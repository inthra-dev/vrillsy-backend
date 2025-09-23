import uuid
import redis
from worker.config import REDIS_URL, LOCK_TTL_S
_r = redis.from_url(REDIS_URL, decode_responses=True)
def _key(job_id: str) -> str: return f"lock:{job_id}"
def acquire_job_lock(job_id: str) -> str | None:
    token = str(uuid.uuid4())
    ok = _r.set(_key(job_id), token, nx=True, ex=LOCK_TTL_S)
    return token if ok else None
def release_job_lock(job_id: str) -> None:
    try: _r.delete(_key(job_id))
    except Exception: pass
def is_locked(job_id: str) -> bool:
    return _r.exists(_key(job_id)) == 1
