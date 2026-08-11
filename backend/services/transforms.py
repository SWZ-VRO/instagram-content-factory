"""
The fixed catalog of variant transforms (§8): crop, zoom, reframe, duration
variation, different start/end point, mirror. Deliberately exactly
MAX_VARIANTS (10) entries so "generate between 5 and 10 variants per master"
maps directly onto "try each transform in order, keep the ones that
succeed" -- see backend/services/variant_generator.py.

Every transform computes its ffmpeg filter in *pixels*, from the master's
own probed width/height/duration (backend/services/ffmpeg_runner.ProbeResult)
-- never as an ffmpeg-side expression. That keeps the generated filter
strings simple, deterministic, and unit-testable without invoking ffmpeg at
all (see tests/test_transforms.py).
"""
from dataclasses import dataclass

from backend.services.ffmpeg_runner import ProbeResult


@dataclass
class TransformPlan:
    vf: str | None = None
    af: str | None = None
    ss: float | None = None  # start offset, seconds
    t: float | None = None  # duration, seconds


@dataclass
class TransformSpec:
    name: str
    build: "callable"


def _even(n: int) -> int:
    """libx264 requires even width/height."""
    n = max(int(n), 2)
    return n if n % 2 == 0 else n - 1


def crop_center(probe: ProbeResult) -> TransformPlan:
    w, h = _even(probe.width * 0.90), _even(probe.height * 0.90)
    x, y = (probe.width - w) // 2, (probe.height - h) // 2
    return TransformPlan(vf=f"crop={w}:{h}:{x}:{y}")


def crop_top_left(probe: ProbeResult) -> TransformPlan:
    w, h = _even(probe.width * 0.85), _even(probe.height * 0.85)
    return TransformPlan(vf=f"crop={w}:{h}:0:0")


def crop_bottom_right(probe: ProbeResult) -> TransformPlan:
    w, h = _even(probe.width * 0.85), _even(probe.height * 0.85)
    x, y = probe.width - w, probe.height - h
    return TransformPlan(vf=f"crop={w}:{h}:{x}:{y}")


def zoom_in(probe: ProbeResult) -> TransformPlan:
    """Scale up 15% then crop back to the original size, centered -- a
    standard, cheap zoom-in effect."""
    scaled_w, scaled_h = _even(probe.width * 1.15), _even(probe.height * 1.15)
    out_w, out_h = _even(probe.width), _even(probe.height)
    x, y = (scaled_w - out_w) // 2, (scaled_h - out_h) // 2
    return TransformPlan(vf=f"scale={scaled_w}:{scaled_h},crop={out_w}:{out_h}:{x}:{y}")


def reframe_vertical(probe: ProbeResult) -> TransformPlan:
    """Crop the largest centered 9:16 region that fits inside the source."""
    target_w_from_h = _even(probe.height * 9 / 16)
    if target_w_from_h <= probe.width:
        w, h = target_w_from_h, _even(probe.height)
    else:
        w, h = _even(probe.width), _even(probe.width * 16 / 9)
    x, y = (probe.width - w) // 2, (probe.height - h) // 2
    return TransformPlan(vf=f"crop={w}:{h}:{x}:{y}")


def mirror_horizontal(probe: ProbeResult) -> TransformPlan:
    return TransformPlan(vf="hflip")


def trim_skip_intro(probe: ProbeResult) -> TransformPlan:
    """Different starting point (§8): skip the first 5%."""
    start = round(probe.duration_seconds * 0.05, 3)
    duration = round(probe.duration_seconds * 0.90, 3)
    return TransformPlan(ss=start, t=duration)


def trim_skip_outro(probe: ProbeResult) -> TransformPlan:
    """Different ending point (§8): cut the last 10%."""
    duration = round(probe.duration_seconds * 0.90, 3)
    return TransformPlan(ss=0.0, t=duration)


def trim_middle_segment(probe: ProbeResult) -> TransformPlan:
    start = round(probe.duration_seconds * 0.05, 3)
    duration = round(probe.duration_seconds * 0.85, 3)
    return TransformPlan(ss=start, t=duration)


def speed_slight_up(probe: ProbeResult) -> TransformPlan:
    """Duration variation via a small, still-natural-looking speed change."""
    return TransformPlan(vf="setpts=PTS/1.05", af="atempo=1.05")


# Exactly MAX_VARIANTS (10) entries by design -- see module docstring.
REGISTRY: list[TransformSpec] = [
    TransformSpec("crop_center", crop_center),
    TransformSpec("crop_top_left", crop_top_left),
    TransformSpec("crop_bottom_right", crop_bottom_right),
    TransformSpec("zoom_in", zoom_in),
    TransformSpec("reframe_vertical", reframe_vertical),
    TransformSpec("mirror_horizontal", mirror_horizontal),
    TransformSpec("trim_skip_intro", trim_skip_intro),
    TransformSpec("trim_skip_outro", trim_skip_outro),
    TransformSpec("trim_middle_segment", trim_middle_segment),
    TransformSpec("speed_slight_up", speed_slight_up),
]


def build_ffmpeg_args(input_path, plan: TransformPlan) -> list[str]:
    """Assemble the full ffmpeg arg list (input seeking + filters + encode
    settings) for one transform plan. Kept separate from ffmpeg_runner so
    the pure argument-building logic is testable without subprocess."""
    args: list[str] = []
    if plan.ss is not None and plan.ss > 0:
        args += ["-ss", f"{plan.ss:.3f}"]
    args += ["-i", str(input_path)]
    if plan.t is not None and plan.t > 0:
        args += ["-t", f"{plan.t:.3f}"]
    if plan.vf:
        args += ["-vf", plan.vf]
    if plan.af:
        args += ["-af", plan.af]
    args += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
    ]
    return args
