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
MIN_CUT_GAP_S = float(os.getenv("MIN_CUT_GAP_S", "0.20"))            # min odstęp między onsets
FALLBACK_INTERVAL_S = float(os.getenv("FALLBACK_INTERVAL_S", "0.50")) # interwał gdy mało beatów

LOCK_TTL_S = 600
WORKER_VERSION = os.getenv("WORKER_VERSION", "vrillsy-D5.0-2025-08-16")

# AUBIO
AUBIO_METHOD = os.getenv("AUBIO_METHOD", "complex")
AUBIO_THRESHOLD = os.getenv("AUBIO_THRESHOLD", "0.35")

# Ścieżki
SHARED_DIR = os.getenv("SHARED_DIR", "/shared")
OUTPUTS_DIR = os.getenv("OUTPUTS_DIR", "/outputs")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Feature flags (opcjonalne)
HOOK_MODE = os.getenv("HOOK_MODE", "A")            # A or B (teaser)
CROSSFADES = os.getenv("CROSSFADES", "0") == "1"   # niewykorzystane w D5 (twarde cięcia domyślnie)
