import os, json, time, subprocess
from datetime import datetime, timezone
from celery.utils.log import get_task_logger
from app.celery_app import celery_app as _celery

log = get_task_logger(__name__)

def _run(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

def _ffprobe_dur(path):
    p = _run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1", path])
    if p.returncode!=0 or not p.stdout.strip(): return None
    try: return float(p.stdout.strip())
    except: return None

def _beats_from_astats(audio_path, target_s, attention_end_s, min_gap=0.2):
    p = _run(["ffmpeg","-hide_banner","-nostats","-i",audio_path,
              "-af","astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level",
              "-f","null","-"])
    stream = p.stderr
    times, levels = [], []
    for ln in stream.splitlines():
        if "pts_time:" in ln and "lavfi.astats.Overall.RMS_level" in ln and "value:" in ln:
            try:
                t = float(ln.split("pts_time:")[1].split()[0].strip(","))
                v = float(ln.split("value:")[1].split()[0].strip(","))
                if 0.0 <= t < target_s:
                    times.append(t); levels.append(v)
            except: pass
    if len(times) < 32:
        return []
    thr = sorted(levels)[int(0.8*len(levels))]
    cand = [times[i] for i,v in enumerate(levels) if v >= thr]
    cand.sort()
    beats, last = [], -1e9
    for t in cand:
        if t <= attention_end_s or t >= target_s: continue
        if t - last >= 0.1:
            beats.append(t); last = t
    pruned, last = [], -1e9
    for t in beats:
        if t - last >= min_gap:
            pruned.append(t); last = t
    return pruned

def plan_timeline_d41(target_s, attention_min=0.25, attention_max=0.30,
                      beats=None, min_cut_gap=0.2, fallback_interval=0.5):
    attention_end = min(1.5, target_s)
    att, t = [], 0.0
    while t + attention_max <= attention_end - 1e-6:
        att.append(attention_max); t += attention_max
    rem = attention_end - t
    if rem > 1e-6:
        if rem < attention_min and att:
            deficit = attention_min - rem
            for i in range(len(att)-1, -1, -1):
                can = att[i] - attention_min
                if can <= 0: continue
                d = min(deficit, can); att[i] -= d; deficit -= d
                if deficit <= 1e-9: break
            att.append(attention_min)
        else:
            att.append(rem)
    fallback_used, used_beats, cuts = False, [], []
    if beats and len(beats) >= 2:
        used_beats = [b for b in beats if attention_end < b < target_s]
        pruned, last = [], attention_end
        for b in used_beats:
            if b - last >= min_cut_gap:
                pruned.append(b); last = b
        cuts = pruned
    else:
        fallback_used = True
        x = attention_end + fallback_interval
        while x < target_s - 1e-6:
            cuts.append(x); x += fallback_interval
    return att, cuts, used_beats, fallback_used, attention_end

def _sync_ratio(cuts, beats, win=0.05):
    if not beats or not cuts: return None
    ok = 0
    for t in cuts:
        nb = min(beats, key=lambda b: abs(b - t))
        if abs(nb - t) <= win: ok += 1
    return ok/len(cuts)

@_celery.task(name="vrillsy.render_job")
def render_job(job_id, audio, videos, out,
               target_duration_s=10.0,
               attention_min_s=0.25, attention_max_s=0.30,
               shuffle=False):
    T0 = time.time()

    # walidacje
    if not isinstance(videos, (list,tuple)) or len(videos) < 2:
        return {"ok": False, "job_id": job_id, "code":"VR-E003","msg":"NOT_ENOUGH_VIDEOS (<2)"}
    if attention_min_s > attention_max_s:
        return {"ok": False, "job_id": job_id, "code":"VR-E005","msg":"INVALID_PAYLOAD attention_min>attention_max"}
    if target_duration_s <= 0:
        return {"ok": False, "job_id": job_id, "code":"VR-E006","msg":"TARGET_TOO_SMALL"}
    if not os.path.exists(audio):
        return {"ok": False, "job_id": job_id, "code":"VR-E001","msg":"AUDIO_NOT_FOUND","audio": audio}
    missing = [v for v in videos if not os.path.exists(v)]
    if missing:
        return {"ok": False, "job_id": job_id, "code":"VR-E002","msg":"VIDEO_NOT_FOUND","missing_count": len(missing), "missing_sample": missing[:3]}

    qa_path = out.replace(".mp4",".json") if out.startswith("/outputs/") else f"/outputs/{job_id}.json"
    try:
        # 1) TRIM audio
        a_trim = f"/outputs/{job_id}_trim.wav"
        p = _run(["ffmpeg","-hide_banner","-y","-i",audio,"-t",f"{target_duration_s:.3f}",
                  "-ac","2","-ar","48000","-c:a","pcm_s16le", a_trim])
        if p.returncode!=0:
            return {"ok": False, "job_id": job_id, "code":"VR-E007","msg":"RENDER_FAIL audio trim","ffmpeg_tail": p.stderr.splitlines()[-30:]}

        # 2) beats
        attention_cap = min(1.5, target_duration_s)
        beats = _beats_from_astats(a_trim, target_duration_s, attention_cap, min_gap=0.2)

        # 3) plan
        att, cuts, used_beats, fallback_used, attention_end = plan_timeline_d41(
            target_s=target_duration_s, attention_min=attention_min_s, attention_max=attention_max_s,
            beats=beats, min_cut_gap=0.2, fallback_interval=0.5
        )

        # 4) segmenty
        cut_pts = [0.0]; s=0.0
        for d in att: s += d; cut_pts.append(round(s,3))
        for c in cuts: cut_pts.append(round(c,3))
        a_dur = _ffprobe_dur(a_trim) or target_duration_s
        cut_pts.append(round(min(target_duration_s, a_dur),3))
        cut_pts = sorted({x for x in cut_pts if x <= target_duration_s + 1e-6})
        segs = []
        for i in range(len(cut_pts)-1):
            d = cut_pts[i+1]-cut_pts[i]
            if d > 1e-3: segs.append(d)

        # 5) render (1080x1920@30, SAR=1)
        tmpd = f"/outputs/{job_id}_tmp"; os.makedirs(tmpd, exist_ok=True)
        seg_files, vi = [], 0
        vf = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(1080-iw)/2:(1920-ih)/2,fps=30,setsar=1"
        for idx, dur in enumerate(segs):
            vpath = videos[vi % len(videos)]; vi += 1
            seg_out = os.path.join(tmpd, f"seg_{idx:03d}.mp4")
            p = _run(["ffmpeg","-hide_banner","-y","-ss","0","-t",f"{dur:.3f}","-i",vpath,"-an","-vf",vf,
                      "-c:v","libx264","-preset","veryfast","-crf","18", seg_out])
            if p.returncode!=0:
                return {"ok": False, "job_id": job_id, "code":"VR-E004","msg":f"VIDEO_BROKEN {vpath}","ffmpeg_tail": p.stderr.splitlines()[-30:]}
            seg_files.append(seg_out)

        # 6) concat + audio + cap
        list_path = os.path.join(tmpd, "list.txt")
        with open(list_path,"w") as f:
            for pth in seg_files: f.write(f"file '{pth}'\n")
        p = _run(["ffmpeg","-hide_banner","-y","-f","concat","-safe","0","-i",list_path,"-i",a_trim,
                  "-r","30","-pix_fmt","yuv420p","-vf","setsar=1",
                  "-c:v","libx264","-preset","veryfast","-crf","18","-c:a","aac",
                  "-shortest","-to",f"{target_duration_s:.3f}", out])
        if p.returncode!=0:
            return {"ok": False, "job_id": job_id, "code":"VR-E007","msg":"RENDER_FAIL final mux","ffmpeg_tail": p.stderr.splitlines()[-30:]}

        dur_out = _ffprobe_dur(out) or 0.0

        # 7) QA
        mae = None
        if used_beats:
            errs = []
            for t in cuts:
                nb = min(beats, key=lambda b: abs(b - t))
                errs.append(abs(nb - t))
            mae = (sum(errs)/len(errs)) if errs else None
        sync = _sync_ratio(cuts, beats)

        qa = {
          "ok": True,
          "job_id": job_id,
          "target_s": float(f"{target_duration_s:.3f}"),
          "duration_out_s": float(f"{dur_out:.3f}"),
          "abs_err_s": float(f"{abs(dur_out-target_duration_s):.3f}"),
          "attention_segments": [float(f"{d:.3f}") for d in att],
          "attention_end_s": float(f"{attention_end:.3f}"),
          "beats_total": len(beats),
          "beats_used": len(used_beats),
          "segments_total": len(segs),
          "fallback_used": bool(fallback_used),
          "mean_abs_err_s": (None if mae is None else float(f"{mae:.3f}")),
          "sync_ratio_005": (None if sync is None else float(f"{sync:.3f}")),
          "profile": "1080x1920@30",
          "pre_time_s": 0.0,
          "worker_version": "d41",
          "timestamp_utc": datetime.now(timezone.utc).isoformat(),
          "elapsed_s": float(f"{time.time()-T0:.3f}")
        }

        with open(qa_path+".tmp","w") as f: json.dump(qa, f, ensure_ascii=False, indent=2)
        os.replace(qa_path+".tmp", qa_path)

        if dur_out > target_duration_s + 0.1:
            return {"ok": False, "job_id": job_id, "code":"VR-E008","msg":"DURATION_CAP_VIOLATION",
                    "duration_out_s": dur_out, "target_s": target_duration_s}

        log.info("[D41] job_id=%s target=%.3f att_end=%.3f beats_total=%d beats_used=%d segs=%d dur=%.3f fallback=%s elapsed=%.3f",
                 job_id, target_duration_s, attention_end, len(beats), len(used_beats), len(segs), dur_out, fallback_used, time.time()-T0)
        return qa

    except Exception as e:
        return {"ok": False, "job_id": job_id, "code":"VR-E009","msg": f"BEAT_PIPELINE_FAIL {type(e).__name__}: {e}"}
