import os, re
from pathlib import Path
from typing import Union

SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")

def sanitize_filename(name: str) -> str:
    name = name.strip().replace(" ", "_")
    name = SAFE_RE.sub("_", name)
    # uniknij pustych nazw
    return name or "file"

def safe_join(base: Union[str, Path], *paths: str) -> Path:
    base_p = Path(base).resolve()
    out = base_p
    for p in paths:
        out = out.joinpath(p)
    out = out.resolve()
    if not str(out).startswith(str(base_p)):
        raise ValueError("Path traversal detected")
    return out

def ensure_dir(p: Union[str, Path]) -> Path:
    pp = Path(p)
    pp.mkdir(parents=True, exist_ok=True)
    return pp
