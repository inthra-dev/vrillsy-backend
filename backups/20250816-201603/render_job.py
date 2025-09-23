import os, json, subprocess, time, tempfile, pathlib, datetime
from celery import shared_task
from worker.config import (
    PROFILE, TARGET_DEFAULT_S, MIN_CUT_GAP_S, FALLBACK_INTERVAL_S,
    SHARED_DIR, OUTPUTS_DIR, WORKER_VERSION,
    AUBIO_METHOD, AUBIO_THRESHOLD
)
from worker.utils.locks import acquire_job_lock, release_job_lock

def run(cmd: str) -> None:
    print("[CMD]", cmd, flush=True)
    res = subprocess.run(cmd, shell=True)
    if res.returncode != 0:
        raise RuntimeError(f"[FFMPEG_FAIL] code={res.returncode}")

def ffprobe_duration(path: str) -> float:
    out = subprocess.check_output(
        f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{path}"',
        shell=True
    ).decode().strip()
    return float(out)

def ffprobe_streams(path: str) -> dict:
    raw = subprocess.check_output(
        f'ffprobe -v error -print_format json -show_streams -show_format "{path}"',
        shell=True
    ).decode()
    import json as _json
    return _json.loads(raw)

def normalize_inputs(job_dir: str, tmpdir: str) -> tuple[list[str], float]:
    vids_in = sorted([str(p) for p in pathlib.Path(job_dir, "video").glob("*") if p.is_file()])
    if not vids_in: raise RuntimeError("Brak plików wejściowych w /video")
    outs = []
    t0 = time.time()
    for i, src in enumerate(vids_in):
        meta = ffprobe_streams(src)
        vs = [s for s in meta.get("streams", []) if s.get("codec_type") == "video"]
        if not vs: continue
        w = int(vs[0]["width"]); h = int(vs[0]["height"])
        if min(w, h) < 720: raise RuntimeError(f"REJECT: {os.path.basename(src)} ma min_dim < 720")
        r = vs[0].get("r_frame_rate", "0/1")
        try:
            num, den = r.split("/"); fps = float(num)/float(den) if float(den) else 0.0
        except Exception: fps = 0.0
        dst = os.path.join(tmpdir, f"norm_{i:02d}.mp4")
        if w == PROFILE.width and h == PROFILE.height and abs(fps - PROFILE.fps) < 0.01:
            run(
                f'ffmpeg -y -i "{src}" -an '
                f'-vf "setsar={PROFILE.sar},fps={PROFILE.fps},format={PROFILE.pix_fmt}" '
                f'-c:v libx264 -preset veryfast -crf 18 "{dst}"'
            ); outs.append(dst); continue
        vf = (
          f'[0:v]scale={PROFILE.width}:{PROFILE.height}:force_original_aspect_ratio=increase,'
          f'boxblur=20:1,crop={PROFILE.width}:{PROFILE.height}[bg];'
          f'[0:v]scale={PROFILE.width}:{PROFILE.height}:force_original_aspect_ratio=decrease[fg];'
          f'[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar={PROFILE.sar},fps={PROFILE.fps},format={PROFILE.pix_fmt}'
        )
        run(f'ffmpeg -y -i "{src}" -an -filter_complex "{vf}" -c:v libx264 -preset veryfast -crf 18 "{dst}"')
        outs.append(dst)
    return outs, (time.time() - t0)

def trim_audio_to_target(audio_in: str, tmpdir: str, target_s: float) -> str:
    out = os.path.join(tmpdir, "audio_trim.wav")
    run(f'ffmpeg -y -i "{audio_in}" -filter_complex "atrim=0:{target_s},asetpts=N/SR/TB" -ar 48000 -ac 2 -c:a pcm_s16le "{out}"')
    return out

def aubio_onsets(audio_path: str) -> list[float]:
    cmd = ["aubioonset","-i",audio_path,"-O",AUBIO_METHOD,"-t",AUBIO_THRESHOLD]
    res = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    onsets=[]
    for line in res.stdout.splitlines():
        line=line.strip()
        try:
            t=float(line)
            if not onsets or (t - onsets[-1]) >= MIN_CUT_GAP_S: onsets.append(t)
        except ValueError:
            continue
    return onsets

def thin_times(times: list[float], min_gap: float) -> list[float]:
    out=[]; last=-1e9
    for t in times:
        if t - last >= min_gap: out.append(t); last=t
    return out

def build_cut_times(target_s: float, onsets: list[float]) -> tuple[list[float], bool, float]:
    attention_end = min(1.5, target_s)
    usable = [t for t in onsets if attention_end < t < target_s]
    usable = thin_times(usable, MIN_CUT_GAP_S)
    fallback=False
    if len(usable) < 2:
        fallback=True
        t = attention_end + 0.5; usable=[]
        while t < target_s: usable.append(t); t += 0.5
        usable = thin_times(usable, MIN_CUT_GAP_S)
    cuts = [0.0, attention_end] + usable + [target_s]
    cuts = sorted(set([round(x,3) for x in cuts if 0.0 <= x <= target_s]))
    return cuts, fallback, attention_end

def render_from_cuts(norm_videos: list[str], audio_trim: str, cuts: list[float], out_tmp: str, tmpdir: str):
    seg_dir = os.path.join(tmpdir, "segs"); os.makedirs(seg_dir, exist_ok=True)
    offsets = [0.0 for _ in norm_videos]
    segments = []
    for i in range(len(cuts)-1):
        start, end = cuts[i], cuts[i+1]; dur = max(0.001, end - start)
        idx = i % len(norm_videos); src = norm_videos[idx]
        off = offsets[idx]; src_dur = ffprobe_duration(src)
        if off + dur > src_dur: off = 0.0; offsets[idx] = 0.0
        seg = os.path.join(seg_dir, f"seg_{i:04d}.mp4")
        run(f'ffmpeg -y -ss {off:.3f} -i "{src}" -t {dur:.3f} -an '
            f'-r {PROFILE.fps} -pix_fmt {PROFILE.pix_fmt} -c:v libx264 -preset veryfast -crf 18 "{seg}"')
        offsets[idx] += dur
        segments.append(seg)
    inputs = " ".join(f'-i "{s}"' for s in segments) + f' -i "{audio_trim}"'
    n = len(segments)
    filt = f'concat=n={n}:v=1:a=0[v]'
    cmd = (
      f'ffmpeg -y {inputs} -filter_complex "{filt}" '
      f'-map "[v]" -map {n}:a:0 -c:v libx264 -preset veryfast -crf 18 '
      f'-pix_fmt {PROFILE.pix_fmt} -r {PROFILE.fps} -c:a aac -b:a 192k -movflags +faststart -shortest "{out_tmp}"'
    )
    run(cmd)

def sync_metrics(cuts: list[float], onsets: list[float]) -> tuple[float|None, float|None]:
    if not onsets: return None, None
    inner = cuts[2:-1] if len(cuts) >= 4 else []
    if not inner: return None, None
    ok=0; errs=[]
    for t in inner:
        d = min(abs(t-b) for b in onsets); errs.append(d)
        if d <= 0.05: ok += 1
    ratio = ok/len(inner) if inner else None
    mean_err = sum(errs)/len(errs) if errs else None
    return ratio, mean_err

@shared_task(name="tasks.assemble.render_job")
def render_job(job_id: str, target_duration_s: float | None = None) -> dict:
    t_start = time.time()
    target = float(target_duration_s or TARGET_DEFAULT_S)
    job_dir = os.path.join(SHARED_DIR, job_id)
    audio_files = sorted([str(p) for p in pathlib.Path(job_dir, "audio").glob("*") if p.is_file()])
    if not audio_files: raise RuntimeError("Brak plików audio dla joba")
    audio_in = audio_files[0]
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    out_mp4  = os.path.join(OUTPUTS_DIR, f"{job_id}.mp4")
    out_tmp  = out_mp4 + ".tmp"
    out_json = os.path.join(OUTPUTS_DIR, f"{job_id}.json")
    out_done = os.path.join(OUTPUTS_DIR, f"{job_id}.done")

    if acquire_job_lock(job_id) is None:
        return {"status":"locked"}

    with tempfile.TemporaryDirectory(prefix=f"{job_id}_", dir=OUTPUTS_DIR) as tmpdir:
        vids, pre_time_s = normalize_inputs(job_dir, tmpdir)
        audio_trim = trim_audio_to_target(audio_in, tmpdir, target)
        onsets = aubio_onsets(audio_trim)
        cuts, fallback_used, attention_end = build_cut_times(target, onsets)
        render_from_cuts(vids, audio_trim, cuts, out_tmp, tmpdir)
        os.replace(out_tmp, out_mp4)

        duration_out = ffprobe_duration(out_mp4)
        diff_s = abs(duration_out - target)
        sync_ratio_005, mean_abs_err_s = sync_metrics(cuts, onsets)
        qa = {
            "target_s": target,
            "duration_out_s": round(duration_out, 3),
            "diff_s": round(diff_s, 3),
            "attention_end_s": round(attention_end, 3),
            "attention_segments": [[0.0, round(attention_end,3)]],
            "beats_total": len(onsets),
            "beats_used": max(0, len(cuts)-3),
            "segments_total": max(0, len(cuts)-1),
            "fallback_used": fallback_used,
            "sync_ratio_005": None if sync_ratio_005 is None else round(sync_ratio_005, 3),
            "mean_abs_err_s": None if mean_abs_err_s is None else round(mean_abs_err_s, 3),
            "profile": f"{PROFILE.width}x{PROFILE.height}@{PROFILE.fps}",
            "pre_time_s": round(pre_time_s, 3),
            "elapsed_s": round(time.time() - t_start, 3),
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "worker_version": WORKER_VERSION
        }
        with open(out_json, "w") as f: json.dump(qa, f, ensure_ascii=False)
        pathlib.Path(out_done).touch()

    release_job_lock(job_id)
    return {"status":"ok","job_id":job_id,"out":out_mp4,"qa":out_json}
