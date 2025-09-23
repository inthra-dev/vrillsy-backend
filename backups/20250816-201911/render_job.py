import os, json, subprocess, time, tempfile, pathlib, datetime, math, random, hashlib
from typing import List, Tuple, Optional
from celery import shared_task
import redis

from worker.config import (
    PROFILE, TARGET_DEFAULT_S, MIN_CUT_GAP_S, FALLBACK_INTERVAL_S,
    SHARED_DIR, OUTPUTS_DIR, WORKER_VERSION, AUBIO_METHOD, AUBIO_THRESHOLD,
    REDIS_URL
)
from worker.utils.locks import acquire_job_lock, release_job_lock

# ========= Utilities =========

_r = redis.from_url(REDIS_URL, decode_responses=True)

def _hk(job_id: str) -> str:
    return f"job:{job_id}"

def _progress(job_id: str, stage: str, pct: int, extra: dict | None = None) -> None:
    d = {"stage": stage, "progress": str(int(pct))}
    if extra:
        for k, v in extra.items():
            d[str(k)] = str(v)
    try:
        _r.hset(_hk(job_id), mapping=d)
    except Exception:
        pass

def run(cmd: str) -> None:
    print("[CMD]", cmd, flush=True)
    res = subprocess.run(cmd, shell=True)
    if res.returncode != 0:
        raise RuntimeError(f"[FFMPEG_FAIL] code={res.returncode}")

def popen_stdout(cmd: list[str]) -> str:
    res = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return res.stdout

def ffprobe_json(path: str) -> dict:
    raw = subprocess.check_output(
        f'ffprobe -v error -print_format json -show_streams -show_format "{path}"',
        shell=True
    ).decode()
    import json as _json
    return _json.loads(raw)

def ffprobe_duration(path: str) -> float:
    out = subprocess.check_output(
        f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{path}"',
        shell=True
    ).decode().strip()
    try:
        return float(out)
    except Exception:
        return 0.0

def seconds_to_frames(s: float) -> int:
    return max(0, int(round(s * PROFILE.fps)))

def frames_to_seconds(fr: int) -> float:
    return fr / PROFILE.fps

def job_seed(job_id: str) -> int:
    h = hashlib.sha256(job_id.encode()).hexdigest()[:8]
    return int(h, 16)

# ========= Normalization =========

def normalize_inputs(job_dir: str, tmpdir: str) -> tuple[list[str], float]:
    vids_in = sorted([str(p) for p in pathlib.Path(job_dir, "video").glob("*") if p.is_file()])
    if not vids_in:
        raise RuntimeError("Brak plików wejściowych w /video")
    outs = []
    t0 = time.time()
    for i, src in enumerate(vids_in):
        meta = ffprobe_json(src)
        vs = [s for s in meta.get("streams", []) if s.get("codec_type") == "video"]
        if not vs:
            continue
        dst = os.path.join(tmpdir, f"norm_{i:02d}.mp4")
        # Scale/crop do 1080x1920, fps=30, yuv420p (z wypełnieniem tłem boxblur)
        vf = (
          f'[0:v]scale={PROFILE.width}:{PROFILE.height}:force_original_aspect_ratio=increase,'
          f'boxblur=20:1,crop={PROFILE.width}:{PROFILE.height}[bg];'
          f'[0:v]scale={PROFILE.width}:{PROFILE.height}:force_original_aspect_ratio=decrease[fg];'
          f'[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar={PROFILE.sar},fps={PROFILE.fps},format={PROFILE.pix_fmt}'
        )
        run(f'ffmpeg -y -i "{src}" -an -filter_complex "{vf}" -c:v libx264 -preset veryfast -crf 18 "{dst}"')
        outs.append(dst)
    return outs, (time.time() - t0)

def prepare_audio(audio_in: str, tmpdir: str, target_s: float) -> str:
    out = os.path.join(tmpdir, "audio_proc.wav")
    safe_len = target_s + 0.2
    af = (
        f"atrim=0:{safe_len},asetpts=N/SR/TB,"
        f"loudnorm=I=-14:TP=-1.5:LRA=11:linear=true:print_format=summary,"
        f"acompressor=threshold=-1.5dB:ratio=4:attack=5:release=50:makeup=0,"
        f"afade=t=in:st=0:d=0.02,afade=t=out:st={safe_len-0.06}:d=0.06"
    )
    run(f'ffmpeg -y -i "{audio_in}" -filter_complex "{af}" -ar 48000 -ac 2 -c:a pcm_s16le "{out}"')
    return out

# ========= Music analysis =========

def aubio_onsets(audio_path: str) -> list[float]:
    cmd = ["aubioonset", "-i", audio_path, "-O", AUBIO_METHOD, "-t", AUBIO_THRESHOLD]
    stdout = popen_stdout(cmd)
    onsets = []
    last = -1e9
    for line in stdout.splitlines():
        s = line.strip()
        try:
            t = float(s)
            if t - last >= MIN_CUT_GAP_S:
                onsets.append(t)
                last = t
        except ValueError:
            continue
    return onsets

def fallback_beats(audio_len: float, start_offset: float, interval: float) -> list[float]:
    t = start_offset
    out = []
    while t < audio_len:
        out.append(round(t, 6))
        t += interval
    return out

def energy_density(times: list[float], window: float = 0.25) -> list[tuple[float,int]]:
    out = []
    for t in times:
        c = 0
        for x in times:
            if abs(x - t) <= window / 2:
                c += 1
        out.append((t, c))
    return out

# ========= Plan generator =========

def choose_hook(onsets: list[float], rng: random.Random, max_len_s: float = 1.5) -> tuple[float, float]:
    if not onsets:
        return 0.0, min(1.5, TARGET_DEFAULT_S)
    tmax = max(onsets[-1], TARGET_DEFAULT_S)
    cutoff = 0.4 * tmax
    cand = [t for t in onsets if t <= cutoff] or onsets
    dens = energy_density(cand, window=0.25)
    dens.sort(key=lambda x: (x[1], -x[0]), reverse=True)
    start = float(dens[0][0])
    hook_len = rng.uniform(0.6, max_len_s)
    end = start + hook_len
    return max(0.0, start), end

def lengths_distribution(rng: random.Random) -> int:
    u = rng.random()
    if u < 0.45:
        return rng.randint(4, 7)
    elif u < 0.85:
        return rng.randint(8, 16)
    else:
        return rng.randint(17, 28)

def build_cut_times(audio_len: float, beats: list[float], start_at: float, target_total: float) -> List[float]:
    times = [0.0]
    for b in beats:
        if start_at <= b <= target_total:
            times.append(float(b))
    if times[-1] < target_total:
        times.append(target_total)
    times = sorted(set([round(t, 6) for t in times if 0 <= t <= target_total]))
    return times

def assign_shots(vids: list[str], rng: random.Random, n: int) -> List[int]:
    order = []
    last = -1
    for _ in range(n):
        choices = list(range(len(vids)))
        if last >= 0 and len(choices) > 1:
            choices.remove(last)
        idx = choices[rng.randrange(len(choices))]
        order.append(idx)
        last = idx
    return order

def smart_span_adjust(src_len: float, want_s: float, rng: random.Random) -> tuple[float,float,bool]:
    if src_len >= want_s + 0.05:
        t0 = max(0.0, rng.uniform(0, max(0.0, src_len - want_s - 0.01)))
        return t0, t0 + want_s, False
    return 0.0, min(src_len, want_s), True

def nearest_beat(t: float, beats: list[float]) -> float:
    if not beats:
        return t
    return min(beats, key=lambda b: abs(b - t))

def cut_log_line(i: int, t0: float, t1: float, beat_ref: float) -> str:
    fr0 = seconds_to_frames(t0); fr1 = seconds_to_frames(t1); frb = seconds_to_frames(beat_ref)
    delta_fr = min(abs(fr0 - frb), abs(fr1 - frb))
    return f"{i:03d} | {t0:7.3f}–{t1:7.3f} s | near_beat={beat_ref:7.3f} s | Δframes={delta_fr}"

# ========= FFMPEG layer =========

def cut_segment(src: str, t0: float, t1: float, out_path: str) -> None:
    dur = max(0.001, t1 - t0)
    vf = f"fps={PROFILE.fps},format={PROFILE.pix_fmt},setsar={PROFILE.sar}"
    run(f'ffmpeg -y -ss {t0:.6f} -i "{src}" -t {dur:.6f} -an -vf "{vf}" -c:v libx264 -preset veryfast -crf 18 "{out_path}"')

def concat_segments(list_path: str, out_path: str) -> None:
    run(f'ffmpeg -y -f concat -safe 0 -i "{list_path}" -c:v libx264 -preset veryfast -crf 18 -pix_fmt {PROFILE.pix_fmt} -r {PROFILE.fps} "{out_path}"')

def mux_with_audio(video_in: str, audio_in: str, out_path: str, target_s: float) -> None:
    run(
        'ffmpeg -y -i "{vin}" -i "{ain}" '
        '-filter_complex "[0:v]fps={fps},format={pix},tpad=stop_mode=clone:stop_duration=0.02[v];'
        '[1:a]atrim=0:{T:.6f},asetpts=N/SR/TB[a]" '
        '-map "[v]" -map "[a]" -t {T:.6f} -pix_fmt {pix} -r {fps} -c:v libx264 -preset veryfast -crf 18 -movflags +faststart "{out}"'
        .format(vin=video_in, ain=audio_in, T=target_s, pix=PROFILE.pix_fmt, fps=PROFILE.fps, out=out_path)
    )

# ========= Main task =========

@shared_task(name="render_job")
def render_job(job_id: str, target_duration_s: float | None = None) -> dict:
    t_start = time.time()
    target = float(target_duration_s or TARGET_DEFAULT_S)
    job_dir = os.path.join(SHARED_DIR, job_id)
    audio_files = sorted([str(p) for p in pathlib.Path(job_dir, "audio").glob("*") if p.is_file()])
    if not audio_files:
        audio_files = sorted([str(p) for p in pathlib.Path(job_dir).glob("*") if p.suffix.lower() in (".wav",".mp3",".m4a",".aac",".flac",".ogg")])
    if not audio_files:
        raise RuntimeError("Brak plików audio dla joba")
    audio_in = audio_files[0]

    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    out_mp4  = os.path.join(OUTPUTS_DIR, f"{job_id}.mp4")
    out_tmpv = out_mp4 + ".vtmp.mp4"
    out_tmpl = out_mp4 + ".list.txt"
    out_json = os.path.join(OUTPUTS_DIR, f"{job_id}.json")
    out_done = os.path.join(OUTPUTS_DIR, f"{job_id}.done")

    if acquire_job_lock(job_id) is None:
        return {"status": "locked"}

    _progress(job_id, "ingest", 3, {"version": WORKER_VERSION})

    rng = random.Random(job_seed(job_id))

    with tempfile.TemporaryDirectory(prefix=f"{job_id}_", dir=OUTPUTS_DIR) as tmpdir:
        # 1) Normalize
        vids, pre_time_s = normalize_inputs(job_dir, tmpdir)
        _progress(job_id, "normalize", 15, {"clips": len(vids)})

        audio_proc = prepare_audio(audio_in, tmpdir, target)
        _progress(job_id, "normalize_audio", 25)

        # 2) Detect beats / onsets
        onsets = aubio_onsets(audio_proc)
        audio_len = ffprobe_duration(audio_proc)
        _progress(job_id, "detect_beats", 35, {"onsets": len(onsets)})

        # 3) Build plan
        hook_start, hook_end = choose_hook(onsets, rng, max_len_s=1.5)
        hook_end = min(hook_end, target)
        beats_after = [t for t in onsets if t > hook_end + 1/PROFILE.fps]
        if len(beats_after) < 4:
            beats_after = fallback_beats(audio_len=target, start_offset=hook_end, interval=FALLBACK_INTERVAL_S)
        cut_times = [0.0, hook_end]
        cut_times.extend([t for t in beats_after if t <= target])
        if cut_times[-1] < target - 1e-3:
            cut_times.append(target)
        cut_times = sorted(set([round(t, 6) for t in cut_times if 0 <= t <= target]))

        refined = [cut_times[0]]
        i = 1
        while i < len(cut_times):
            last = refined[-1]
            want_fr = lengths_distribution(rng)
            want_s = frames_to_seconds(want_fr)
            desired_end = last + want_s
            nb = min(cut_times[1:], key=lambda b: abs(b - desired_end)) if len(cut_times) > 1 else desired_end
            if nb <= last + (2/PROFILE.fps):
                j = i
                while j < len(cut_times) and cut_times[j] <= last + (2/PROFILE.fps):
                    j += 1
                if j >= len(cut_times):
                    break
                refined.append(cut_times[j]); i = j + 1
            else:
                refined.append(nb)
                while i < len(cut_times) and cut_times[i] <= nb + 1e-6:
                    i += 1

        if refined[-1] < target - 1e-3:
            refined.append(target)

        order = assign_shots(vids, rng, n=max(1, len(refined)-1))
        _progress(job_id, "plan", 50, {"cuts": len(refined)-1})

        # 4) Cut segments
        segments = []
        cutlog = []
        for idx in range(len(refined)-1):
            t0 = refined[idx]; t1 = refined[idx+1]
            src = vids[order[idx]]
            src_len = ffprobe_duration(src)
            want = max(1/PROFILE.fps, t1 - t0)
            s0, s1, need_rev = smart_span_adjust(src_len, want, rng)
            seg_path = os.path.join(tmpdir, f"seg_{idx:03d}.mp4")
            cut_segment(src, s0, s1, seg_path)
            if need_rev and (s1 - s0) < want - (1/PROFILE.fps):
                seg_rev = os.path.join(tmpdir, f"seg_{idx:03d}_r.mp4")
                run(f'ffmpeg -y -i "{seg_path}" -vf "reverse,fps={PROFILE.fps},format={PROFILE.pix_fmt}" -an -c:v libx264 -preset veryfast -crf 18 "{seg_rev}"')
                lst = os.path.join(tmpdir, f"seg_{idx:03d}.lst")
                with open(lst, "w") as f:
                    f.write(f"file '{seg_path}'\n")
                    f.write(f"file '{seg_rev}'\n")
                run(f'ffmpeg -y -f concat -safe 0 -i "{lst}" -c:v libx264 -preset veryfast -crf 18 -pix_fmt {PROFILE.pix_fmt} -r {PROFILE.fps} "{seg_path}"')

            segments.append(seg_path)
            beat_ref = min(onsets, key=lambda b: abs(b - t1)) if onsets else t1
            cutlog.append(cut_log_line(idx, t0, t1, beat_ref))
        _progress(job_id, "cut", 70)

        # 5) Concat video-only
        with open(out_tmpl, "w") as f:
            for p in segments:
                f.write(f"file '{p}'\n")
        concat_segments(out_tmpl, out_tmpv)
        _progress(job_id, "mux_prep", 80)

        # 6) Mux + clamp to exact target
        mux_with_audio(out_tmpv, audio_proc, out_mp4, target)
        _progress(job_id, "finalize", 95)

        # QA & logs
        d_out = ffprobe_duration(out_mp4)
        qa = {
            "job_id": job_id,
            "out": out_mp4,
            "duration_s": round(d_out, 3),
            "profile": f"{PROFILE.width}x{PROFILE.height}@{PROFILE.fps}",
            "cuts": len(refined)-1,
            "onsets": len(onsets),
            "hook": {"start_s": round(hook_start,3), "end_s": round(hook_end,3)},
            "cutlog": cutlog[:500],
            "pre_time_s": round(pre_time_s, 3),
            "elapsed_s": round(time.time() - t_start, 3),
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "worker_version": WORKER_VERSION
        }
        with open(out_json, "w") as f:
            json.dump(qa, f, ensure_ascii=False, indent=2)
        pathlib.Path(out_done).touch()

    release_job_lock(job_id)
    _progress(job_id, "done", 100)
    return {"status": "ok", "job_id": job_id, "out": out_mp4, "qa": out_json}
