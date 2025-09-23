from __future__ import annotations
import json, subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List
from app.celeryapp import celery_app
from app.config import get_settings

@dataclass
class Manifest:
    job_id: str
    audio_path: Path
    video_paths: List[Path]
    out_dir: Path

def _load_manifest(job_id: str) -> Manifest:
    s = get_settings()
    job_dir = Path(s.SHARED_DIR) / job_id
    data = json.loads((job_dir / "manifest.json").read_text())
    return Manifest(
        job_id=job_id,
        audio_path=Path(data["files"]["audio"]["saved"]),
        video_paths=[Path(v["saved"]) for v in data["files"]["videos"]],
        out_dir=job_dir,
    )

def _run(cmd: List[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}):\n{proc.stdout[:4000]}")

def _build_ffmpeg_command(man: Manifest) -> (List[str], Path, Path):
    inputs: List[str] = []
    # input 0: audio
    inputs += ["-i", str(man.audio_path)]
    # input 1..N: video
    for v in man.video_paths:
        inputs += ["-i", str(v)]

    n = len(man.video_paths)
    if n < 1:
        raise ValueError("No videos provided")

    parts: List[str] = []
    labels: List[str] = []
    # normalize all videos to 1080x1920@30, SAR=1
    for idx in range(n):
        in_label = f"{idx+1}:v"  # stream labels: 0 is audio
        out_label = f"v{idx+1}"
        parts.append(
            f"[{in_label}]scale=1080:-2:flags=lanczos,"
            f"pad=1080:1920:(1080-iw)/2:(1920-ih)/2:color=black,"
            f"fps=30,setsar=1[{out_label}]"
        )
        labels.append(f"[{out_label}]")

    if n == 1:
        parts.append(f"{labels[0]}trim=duration=10,setpts=PTS-STARTPTS[vout]")
    else:
        parts.append(f"{''.join(labels)}concat=n={n}:v=1:a=0,trim=duration=10,setpts=PTS-STARTPTS[vout]")

    filter_complex = ";".join(parts)

    out_final = man.out_dir / "final.mp4"
    out_tmp = man.out_dir / "final.tmp.mp4"

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "0:a:0",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-shortest", "-t", "10",
        str(out_tmp),
    ]
    return cmd, out_tmp, out_final

@celery_app.task(name="render_job")
def render_job(job_id: str):
    s = get_settings()
    job_dir = Path(s.SHARED_DIR) / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # health marker
    (job_dir / "_worker_touched").write_text("ok")

    man = _load_manifest(job_id)
    cmd, out_tmp, out_final = _build_ffmpeg_command(man)

    # render to temp file
    _run(cmd)

    # atomic rename only after success
    if out_tmp.exists() and out_tmp.stat().st_size > 0:
        out_tmp.replace(out_final)
    else:
        raise RuntimeError("Temporary output not created or empty")

    # write status after file is complete
    (job_dir / "status.json").write_text(json.dumps({"ok": True, "job_id": job_id, "output": str(out_final)}))
    return {"ok": True, "job_id": job_id, "output": str(out_final)}
