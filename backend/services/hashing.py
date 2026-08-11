"""
Duplicate detection primitives (§14): SHA256 for exact-file matches,
perceptual hash (of a representative frame) for "same video, re-encoded or
renamed" matches that a simple checksum would miss.
"""
import hashlib
import tempfile
from pathlib import Path

import imagehash
from PIL import Image

from backend.services import ffmpeg_runner


def sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def perceptual_hash_of_video(path: Path, *, duration_seconds: float) -> str:
    """
    Perceptual hash of a single frame taken at the video's midpoint. One
    frame is enough to catch "this is the same source clip" (the actual use
    case here -- catching renamed/re-encoded re-imports, per §14) without
    the cost of hashing every frame; it is NOT meant to catch two
    completely different edits of the same footage.
    """
    midpoint = max(duration_seconds / 2, 0.0)
    with tempfile.TemporaryDirectory(prefix="icf_phash_") as tmp:
        frame_path = Path(tmp) / "frame.jpg"
        ffmpeg_runner.extract_frame(path, frame_path, at_seconds=midpoint)
        with Image.open(frame_path) as img:
            return str(imagehash.phash(img))


def hamming_distance(hash_a: str, hash_b: str) -> int:
    """Distance between two hex perceptual hashes, as produced by
    perceptual_hash_of_video. Lower = more visually similar."""
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)
