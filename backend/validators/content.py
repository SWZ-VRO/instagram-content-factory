"""
Content-side validators used by the (Phase 2) watcher and QC step. Kept as a
separate layer per §41 so services/repositories stay free of "is this file
actually usable" logic.
"""
from pathlib import Path

ALLOWED_MASTER_EXTENSIONS = {".mp4", ".mov"}


def is_supported_video_file(path: Path) -> bool:
    return path.suffix.lower() in ALLOWED_MASTER_EXTENSIONS


def is_nonempty_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0
