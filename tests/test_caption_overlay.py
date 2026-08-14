"""
backend/services/caption_overlay.py -- pure text-wrapping and filter-string
logic, no ffmpeg needed (see test_caption_pipeline.py for the orchestration
that actually invokes it, with ffmpeg mocked).
"""
from pathlib import Path

from backend.core.config import settings
from backend.services.caption_overlay import build_overlay_filter, wrap_caption_text


def test_short_caption_fits_on_one_line():
    result = wrap_caption_text("Hello world", max_chars_per_line=26, max_lines=4)
    assert result == "Hello world"


def test_long_caption_wraps_across_multiple_lines():
    text = "This is a much longer caption that will not fit on a single line"
    result = wrap_caption_text(text, max_chars_per_line=20, max_lines=10)
    lines = result.split("\n")
    assert len(lines) > 1
    assert all(len(line) <= 20 for line in lines)
    # nothing truncated (max_lines is generous here) -- words survive in order
    assert " ".join(lines).split() == text.split()


def test_overly_long_caption_is_truncated_with_ellipsis():
    text = " ".join(["word"] * 50)
    result = wrap_caption_text(text, max_chars_per_line=10, max_lines=2)
    lines = result.split("\n")
    assert len(lines) == 2
    assert lines[-1].endswith("…")


def test_single_very_long_word_does_not_infinite_loop():
    """A pathological single word longer than max_chars_per_line must still
    terminate (placed on its own line) rather than loop forever."""
    text = "a" * 100
    result = wrap_caption_text(text, max_chars_per_line=10, max_lines=2)
    assert result  # terminates, produces something


def test_build_overlay_filter_includes_expected_drawtext_options(tmp_path):
    textfile = tmp_path / "caption.txt"
    textfile.write_text("Hello")
    filt = build_overlay_filter(video_height=1920, textfile_path=textfile)

    assert filt.startswith("drawtext=")
    assert f"fontfile='{settings.CAPTION_FONT_PATH}'" in filt
    assert "fontcolor=white" in filt
    assert "box=1" in filt
    assert "boxcolor=black@0.55" in filt
    # fontsize scales with video height
    assert f"fontsize={int(1920 * settings.CAPTION_FONT_SIZE_RATIO)}" in filt


def test_build_overlay_filter_fontsize_scales_with_video_height(tmp_path):
    textfile = tmp_path / "caption.txt"
    textfile.write_text("Hello")
    small = build_overlay_filter(video_height=480, textfile_path=textfile)
    large = build_overlay_filter(video_height=1920, textfile_path=textfile)

    def _fontsize(filt: str) -> int:
        marker = "fontsize="
        start = filt.index(marker) + len(marker)
        end = filt.index(":", start)
        return int(filt[start:end])

    assert _fontsize(large) > _fontsize(small)
