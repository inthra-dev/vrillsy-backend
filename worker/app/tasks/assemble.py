from __future__ import annotations
import os, tempfile, subprocess, shlex
from typing import List, Dict
from app.celery_app import celery_app

def _run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({p.returncode}):\n{p.stdout}")

@celery_app.task(name="vrillsy.render_job")
def render_job(job_id: str, audio_path: str, video_paths: List[str], out_dir: str = "/app/outputs") -> Dict:
    os.makedirs(out_dir, exist_ok=True)
    if not video_paths:
        raise ValueError("video_paths empty")
    # lista do concat demuxer (działa gdy kodeki są zgodne — w naszych próbkach są)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for vp in video_paths:
            f.write(f"file {shlex.quote(vp)}\n")
        list_path = f.name
    out_path = os.path.join(out_dir, f"{job_id}_final.mp4")
    # sklej wideo, przytnij do 10s, skaluj do 1080x1920, dołóż audio, zakończ na najkrótszym
    cmd = [
        "ffmpeg","-y",
        "-f","concat","-safe","0","-i", list_path,
        "-i", audio_path,
        "-t","10",
        "-vf","scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1",
        "-map","0:v:0","-map","1:a:0",
        "-c:v","libx264","-pix_fmt","yuv420p","-profile:v","high","-r","30",
        "-c:a","aac","-b:a","128k",
        "-shortest","-movflags","+faststart",
        out_path
    ]
    try:
        _run(cmd)
    finally:
        try: os.remove(list_path)
        except Exception: pass
    ok = os.path.exists(out_path) and os.path.getsize(out_path) > 0
    return {"ok": ok, "output": out_path, "frames": 300, "job_id": job_id}
