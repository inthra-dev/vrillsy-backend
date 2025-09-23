import json, os, time
from .celery_app import app

@app.task(name="vrillsy.render", queue="vrillsy")
def render(job_id:str, target_s:float=10.0):
    t0=time.time()
    qa={
        "job_id": job_id,
        "target_s": target_s,
        "duration_out_s": target_s,
        "attention_end_s": 1.0,
        "beats_total": 0,
        "beats_used": 0,
        "segments_total": 0,
        "fallback_used": True,
        "sync_ratio_005": None,
        "elapsed_s": None,
        "status": "SUCCESS-STUB"
    }
    qa["elapsed_s"]=round(time.time()-t0,3)
    outdir=os.path.join(os.environ.get("OUTPUT_DIR","/app/outputs"), job_id)
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir,"qa.json"),"w") as f:
        json.dump(qa,f,indent=2)
    open(os.path.join(outdir,"final.mp4"),"wb").close()
    return qa
