import os
from typing import Dict
import soundfile as sf
from .assemble import assemble_videos_for_cuts  # dostosuj nazwę jeśli inna
from ..celery_app import celery_app
from ..utils.cut_strategies import load_cfg, detect_beats_and_onsets, pro_cutplan

@celery_app.task(name="tasks.pro_render.render_job_pro")
def render_job_pro(job_id: str, attention_min_s: float, attention_max_s: float, shuffle: bool=False, order=None) -> Dict:
    job_root = f"/app/shared/{job_id}"
    audio_dir = os.path.join(job_root, "audio")
    video_dir = os.path.join(job_root, "video")
    outputs = "/outputs"
    os.makedirs(outputs, exist_ok=True)

    audios = [f for f in os.listdir(audio_dir) if f.lower().endswith((".mp3",".wav",".m4a",".flac",".ogg"))]
    if len(audios)!=1: raise ValueError("no_or_multiple_audio")
    audio_path = os.path.join(audio_dir, audios[0])

    y, sr = sf.read(audio_path, always_2d=False)
    try:
        import numpy as np
        if getattr(y, "ndim", 1) > 1:
            y = np.mean(y, axis=1).astype("float32")
        else:
            y = y.astype("float32", copy=False)
    except Exception:
        pass

    beat_times, onsets = detect_beats_and_onsets(y, sr)
    cfg = load_cfg(os.path.join(job_root, "config.json"))
    cuts = pro_cutplan(beat_times, onsets, cfg, total_duration=float(len(y)/sr))

    vids = [os.path.join(video_dir, v) for v in sorted(os.listdir(video_dir)) if v.lower().endswith((".mp4",".mov",".mkv",".webm"))]
    if not vids: raise ValueError("no_video")

    out = os.path.join(outputs, f"{job_id}.mp4")
    segments_total, beats_used = assemble_videos_for_cuts(vids, cuts, out, attention_min_s, attention_max_s, shuffle=shuffle, order=order)

    return {
        "job_id": job_id,
        "output": out,
        "cuts": len(cuts)-1,
        "beats_used": int(beats_used) if isinstance(beats_used,(int,float)) else beats_used,
        "duration_s": cuts[-1],
        "clips_in": len(vids),
        "segments_total": segments_total,
        "strategy": "pro"
    }
