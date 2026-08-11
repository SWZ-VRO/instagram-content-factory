"""
Quality control (§10 step 7, §14 "un simple changement de nom ne doit
jamais permettre de contourner la détection"). Two checks:

  - check_master_integrity: run BEFORE a dropped file is trusted at all --
    right extension, non-empty, ffprobe can actually read it, has a video
    stream, sane duration.
  - check_variant_output: run AFTER a transform produces a file -- lighter,
    since the source was already validated; mainly guards against ffmpeg
    reporting success while producing a broken/empty file.
"""
from dataclasses import dataclass, field
from pathlib import Path

from backend.core.config import settings
from backend.services import ffmpeg_runner
from backend.validators.content import is_nonempty_file, is_supported_video_file


@dataclass
class QCResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    probe: ffmpeg_runner.ProbeResult | None = None


def check_master_integrity(path: Path) -> QCResult:
    reasons: list[str] = []
    if not is_supported_video_file(path):
        reasons.append(f"unsupported extension: {path.suffix}")
    if not is_nonempty_file(path):
        reasons.append("file is empty or missing")
    if reasons:
        return QCResult(passed=False, reasons=reasons)

    try:
        probe = ffmpeg_runner.probe(path)
    except ffmpeg_runner.FFmpegError as exc:
        return QCResult(passed=False, reasons=[f"unreadable/corrupt media: {exc}"])

    if not probe.has_video_stream:
        reasons.append("no video stream found")
    if probe.width <= 0 or probe.height <= 0:
        reasons.append("invalid video dimensions")
    if probe.duration_seconds < settings.MIN_MASTER_DURATION_SECONDS:
        reasons.append(
            f"duration {probe.duration_seconds:.2f}s below minimum {settings.MIN_MASTER_DURATION_SECONDS}s"
        )
    if probe.duration_seconds > settings.MAX_MASTER_DURATION_SECONDS:
        reasons.append(
            f"duration {probe.duration_seconds:.2f}s exceeds maximum {settings.MAX_MASTER_DURATION_SECONDS}s"
        )

    return QCResult(passed=not reasons, reasons=reasons, probe=probe)


def check_variant_output(path: Path) -> QCResult:
    if not is_nonempty_file(path):
        return QCResult(passed=False, reasons=["generated variant is empty or missing"])
    try:
        probe = ffmpeg_runner.probe(path)
    except ffmpeg_runner.FFmpegError as exc:
        return QCResult(passed=False, reasons=[f"generated variant is unreadable: {exc}"])
    if not probe.has_video_stream or probe.duration_seconds <= 0:
        return QCResult(passed=False, reasons=["generated variant has no usable video stream"], probe=probe)
    return QCResult(passed=True, probe=probe)
