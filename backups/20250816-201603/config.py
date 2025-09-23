from dataclasses import dataclass
import os
@dataclass(frozen=True)
class VideoProfile:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    pix_fmt: str = "yuv420p"
    sar: int = 1
PROFILE = VideoProfile()
TARGET_DEFAULT_S = float(os.getenv("TARGET_DURATION_S", "10.0"))
MIN_CUT_GAP_S = 0.2
FALLBACK_INTERVAL_S = 0.5
LOCK_TTL_S = 600
WORKER_VERSION = os.getenv("WORKER_VERSION", "vrillsy-D4.2-2025-08-16")
AUBIO_METHOD = "complex"
AUBIO_THRESHOLD = "0.35"
# Nie wymuszamy -M/--minioi w CLI (różnice wersji). Min-gap zabezpieczamy w kodzie.
SHARED_DIR = os.getenv("SHARED_DIR", "/shared")
OUTPUTS_DIR = os.getenv("OUTPUTS_DIR", "/outputs")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
