import json
from typing import Dict, Iterable, List, Tuple
from fastapi import UploadFile, HTTPException, status
from .paths import sanitize_filename
from .. import config as config_mod

# Strumieniowy zapis z liczeniem bajtów i limitowaniem łącznego rozmiaru
def save_streaming(
    upload: UploadFile,
    dst_path: str,
    total_counter: Dict[str, int],
) -> Tuple[int, str]:
    CHUNK = 1024 * 1024  # 1 MiB
    size = 0
    with open(dst_path, "wb") as f:
        while True:
            chunk = upload.file.read(CHUNK)
            if not chunk:
                break
            size += len(chunk)
            total_counter["bytes"] += len(chunk)
            settings = config_mod.get_settings()
            if total_counter["bytes"] > settings.MAX_TOTAL_UPLOAD_MB * 1024 * 1024:
                # przerwij zapis i zgłoś 413
                f.flush()
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail={"ok": False, "error": "payload_too_large", "limit_mb": settings.MAX_TOTAL_UPLOAD_MB},
                )
            f.write(chunk)
    return size, sanitize_filename(upload.filename or "file")

def serialize_manifest(manifest: dict, manifest_path: str) -> None:
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
