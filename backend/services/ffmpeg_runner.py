"""
Thin, explicit wrapper around the `ffmpeg`/`ffprobe` binaries. Every other
module in the video pipeline (transforms.py, hashing.py, qc.py) goes through
here rather than shelling out itself, so there is exactly one place that
knows how to invoke FFmpeg, one place to mock in tests, and one place to fix
if the binary path/timeout ever needs to change.

FFmpeg is installed as a system package in backend/Dockerfile (`apt-get
install ffmpeg`), NOT via pip -- there is no reliable "ffmpeg" wheel. This
module is unusable without that binary on PATH; every public function raises
FFmpegNotAvailable immediately (not a confusing subprocess traceback) if
it's missing.
"""
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from backend.core.config import settings


class FFmpegError(Exception):
    """FFmpeg/ffprobe ran but exited non-zero, or produced unparseable output."""


class FFmpegNotAvailable(Exception):
    """The ffmpeg/ffprobe binary isn't on PATH. Real in local dev (this repo
    was built and unit-tested on a machine without FFmpeg installed -- see
    README "Tests"); always available inside the Docker image."""


@dataclass
class ProbeResult:
    duration_seconds: float
    width: int
    height: int
    has_video_stream: bool
    has_audio_stream: bool


def _require_binary(binary: str) -> str:
    path = shutil.which(binary)
    if path is None:
        raise FFmpegNotAvailable(f"'{binary}' not found on PATH")
    return path


def probe(input_path: Path) -> ProbeResult:
    """Run ffprobe and extract exactly what the QC/transform layers need.
    Raises FFmpegError if the file isn't a readable media file (e.g. a
    truncated upload, a non-video file dropped by mistake)."""
    binary = _require_binary(settings.FFPROBE_BINARY)
    cmd = [
        binary,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(input_path),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=settings.FFMPEG_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"ffprobe timed out probing {input_path.name}") from exc

    if proc.returncode != 0:
        raise FFmpegError(f"ffprobe failed on {input_path.name}: {proc.stderr.strip()}")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise FFmpegError(f"ffprobe produced unparseable output for {input_path.name}") from exc

    streams = data.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

    fmt = data.get("format", {})
    try:
        duration = float(fmt.get("duration", 0.0))
    except (TypeError, ValueError):
        duration = 0.0

    width = int(video_streams[0].get("width", 0)) if video_streams else 0
    height = int(video_streams[0].get("height", 0)) if video_streams else 0

    return ProbeResult(
        duration_seconds=duration,
        width=width,
        height=height,
        has_video_stream=bool(video_streams),
        has_audio_stream=bool(audio_streams),
    )


def run_ffmpeg(args: list[str], *, output_path: Path) -> None:
    """Run `ffmpeg -y <args>`. `args` must NOT include the leading binary
    name, `-y`, or the output path -- callers (transforms.py) build the
    filter/trim arguments only; this centralizes the invocation."""
    binary = _require_binary(settings.FFMPEG_BINARY)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [binary, "-y", *args, str(output_path)]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=settings.FFMPEG_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"ffmpeg timed out producing {output_path.name}") from exc

    if proc.returncode != 0:
        raise FFmpegError(f"ffmpeg failed producing {output_path.name}: {proc.stderr.strip()[-2000:]}")

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise FFmpegError(f"ffmpeg reported success but produced no output for {output_path.name}")


def extract_frame(input_path: Path, output_jpg: Path, *, at_seconds: float) -> None:
    """Grab a single representative frame for perceptual hashing (hashing.py)."""
    binary = _require_binary(settings.FFMPEG_BINARY)
    output_jpg.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        binary,
        "-y",
        "-ss",
        f"{max(at_seconds, 0):.3f}",
        "-i",
        str(input_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(output_jpg),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=settings.FFMPEG_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"ffmpeg timed out extracting a frame from {input_path.name}") from exc

    if proc.returncode != 0 or not output_jpg.exists():
        raise FFmpegError(f"ffmpeg failed extracting a frame from {input_path.name}: {proc.stderr.strip()[-2000:]}")
