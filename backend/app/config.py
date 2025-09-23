from functools import lru_cache
from typing import List
from pydantic import EmailStr
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Katalog współdzielony na joby
    SHARED_DIR: str = "shared"
    # Limity
    MAX_VIDEOS: int = 20
    MAX_TOTAL_UPLOAD_MB: int = 512  # MiB, audio+video łącznie
    # MIME
    ALLOWED_VIDEO_MIME: List[str] = [
        "video/mp4", "video/quicktime", "video/x-matroska", "video/webm", "video/x-msvideo"
    ]
    ALLOWED_AUDIO_MIME: List[str] = [
        "audio/mpeg", "audio/wav", "audio/x-wav", "audio/flac", "audio/mp4", "audio/aac", "audio/ogg"
    ]
    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_BACKEND_URL: str = "redis://redis:6379/1"

    # Pydantic v2 config
    model_config = SettingsConfigDict(
        env_prefix="VRS_",
        case_sensitive=False,
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()
