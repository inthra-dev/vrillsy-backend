from app.celery_app import celery_app
import os, subprocess
from typing import List

def run(cmd: list[str]) -> None:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed:\n" + p.stderr)

@celery_app.task(name="vrillsy.render_job", queue="vrillsy", bind=True)
def render_job(self, job_id: str, audio_path: str, video_paths: List[str], out_dir: str = "/outputs"):
    os.makedirs(out_dir, exist_ok=True)
    vids = [v for v in video_paths if v][:3]
    if not vids:
        raise ValueError("video_paths is empty")
    out = os.path.join(out_dir, f"{job_id}_final.mp4")

    # ~3.33 s z każdego klipu, wyśrodkowane do 720x1080, 30 fps
    seg = 3.33
    inputs, trims = [], []
    for i, vp in enumerate(vids):
        inputs += ["-i", vp]
        trims.append(
            f"[{i}:v]trim=0:{seg},setpts=PTS-STARTPTS,"
            f"scale=720:1080:force_original_aspect_ratio=decrease,"
            f"pad=720:1080:(ow-iw)/2:(oh-ih)/2,"
            f"fps=30[v{i}]"
        )

    vlist = "".join(f"[v{i}]" for i in range(len(vids)))
    vf = f"{';'.join(trims)};{vlist}concat=n={len(vids)}:v=1:a=0[vout]"
    a_idx = len(vids)  # audio jako ostatni input

    cmd = [
        "ffmpeg","-y",
        *inputs, "-i", audio_path,
        "-filter_complex", vf,
        "-map","[vout]","-map", f"{a_idx}:a:0",
        "-shortest",
        "-r","30","-pix_fmt","yuv420p",
        "-c:v","libx264","-preset","veryfast","-crf","23",
        "-c:a","aac","-b:a","192k",
        "-movflags","+faststart",
        out,
    ]
    run(cmd)
    return {"ok": True, "out": out}
