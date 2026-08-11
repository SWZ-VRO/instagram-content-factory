"""
Pure logic tests for the transform catalog (§8) -- no ffmpeg binary needed,
since every transform computes pixel values in Python from a probed
width/height/duration and only emits a filter *string* for ffmpeg to run
later. See backend/services/transforms.py.
"""
from backend.core.config import settings
from backend.services import transforms
from backend.services.ffmpeg_runner import ProbeResult

PROBE = ProbeResult(duration_seconds=20.0, width=1920, height=1080, has_video_stream=True, has_audio_stream=True)


def _parse_crop(vf: str) -> tuple[int, int, int, int]:
    crop_expr = [part for part in vf.split(",") if part.startswith("crop=")][0]
    w, h, x, y = (int(v) for v in crop_expr.removeprefix("crop=").split(":"))
    return w, h, x, y


def test_registry_has_exactly_max_variants_entries():
    assert len(transforms.REGISTRY) == settings.MAX_VARIANTS


def test_registry_names_are_unique():
    names = [t.name for t in transforms.REGISTRY]
    assert len(names) == len(set(names))


def test_crop_center_is_smaller_than_source_and_centered_and_even():
    plan = transforms.crop_center(PROBE)
    w, h, x, y = _parse_crop(plan.vf)
    assert w % 2 == 0 and h % 2 == 0
    assert w < PROBE.width and h < PROBE.height
    assert x == (PROBE.width - w) // 2
    assert y == (PROBE.height - h) // 2


def test_crop_top_left_is_anchored_at_origin():
    plan = transforms.crop_top_left(PROBE)
    _, _, x, y = _parse_crop(plan.vf)
    assert (x, y) == (0, 0)


def test_zoom_in_crops_back_to_original_even_dimensions():
    plan = transforms.zoom_in(PROBE)
    assert "scale=" in plan.vf
    w, h, _, _ = _parse_crop(plan.vf)
    assert w == transforms._even(PROBE.width)
    assert h == transforms._even(PROBE.height)


def test_reframe_vertical_is_roughly_9_16():
    plan = transforms.reframe_vertical(PROBE)
    w, h, _, _ = _parse_crop(plan.vf)
    assert abs((w / h) - 9 / 16) < 0.02


def test_mirror_horizontal_uses_hflip_only():
    plan = transforms.mirror_horizontal(PROBE)
    assert plan.vf == "hflip"
    assert plan.ss is None and plan.t is None


def test_trim_transforms_stay_within_source_duration():
    for builder in (transforms.trim_skip_intro, transforms.trim_skip_outro, transforms.trim_middle_segment):
        plan = builder(PROBE)
        assert plan.ss is None or plan.ss >= 0
        if plan.ss is not None and plan.t is not None:
            assert plan.ss + plan.t <= PROBE.duration_seconds + 0.01


def test_speed_slight_up_adjusts_both_video_and_audio():
    plan = transforms.speed_slight_up(PROBE)
    assert "setpts" in plan.vf
    assert "atempo" in plan.af


def test_build_ffmpeg_args_uses_input_seeking_when_start_offset_present():
    plan = transforms.TransformPlan(ss=2.0, t=5.0, vf="hflip")
    args = transforms.build_ffmpeg_args("in.mp4", plan)
    assert args.index("-ss") < args.index("-i")
    assert "-t" in args and "-vf" in args


def test_build_ffmpeg_args_omits_ss_when_absent():
    plan = transforms.TransformPlan(vf="hflip")
    args = transforms.build_ffmpeg_args("in.mp4", plan)
    assert "-ss" not in args
    assert args[0] == "-i"


def test_all_registry_transforms_build_valid_plans_for_a_typical_source():
    """Every transform must produce a usable plan for an ordinary 1080p
    source -- no crashes, no zero/negative dimensions."""
    for spec in transforms.REGISTRY:
        plan = spec.build(PROBE)
        args = transforms.build_ffmpeg_args("in.mp4", plan)
        assert "-i" in args
        if plan.vf and "crop=" in plan.vf:
            w, h, _, _ = _parse_crop(plan.vf)
            assert w > 0 and h > 0
