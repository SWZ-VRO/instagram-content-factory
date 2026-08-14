"""
Burns caption text onto a variant video -- the native TikTok/Reels "typed
on iPhone" look: bold white text on a dark semi-transparent box. Runs as a
second FFmpeg pass, after a variant is transformed (transforms.py) and its
caption text is known (repositories/caption_repo.py) -- see
backend/services/caption_pipeline.py for how the two are wired together.

Design notes:
  - Uses `textfile=` (a temp file) rather than embedding the caption in the
    drawtext `text=` parameter directly -- FFmpeg's filtergraph mini-syntax
    treats `:`, `,`, `'` and backslashes as structural characters, and hand-escaping
    arbitrary user-supplied caption text for it is fragile. A separate file
    sidesteps nearly all of that.
  - DejaVu Sans Bold (installed via apt in backend/Dockerfile) stands in for
    SF Pro Bold -- Apple's font isn't redistributable, DejaVu Bold is a
    visually close, openly-licensed match (same humanist-sans proportions).
  - The overlay shows a SHORT excerpt (wrapped/truncated to
    CAPTION_MAX_LINES x CAPTION_MAX_CHARS_PER_LINE), not necessarily the
    full caption -- matches how real "text hook" reels work (a punchy line
    or two on-screen, the full text lives in the post's actual caption
    field, which is never touched -- §11, exact text, always).
  - This is a styling choice on top of already-legitimate content variation,
    not a detection-evasion technique (see conversation notes: a real
    "video spoofer" integration was declined for exactly that distinction).
"""
import tempfile
from pathlib import Path

from backend.core.config import settings
from backend.services.ffmpeg_runner import ProbeResult, run_ffmpeg


def wrap_caption_text(text: str, *, max_chars_per_line: int, max_lines: int) -> str:
    """Greedy word-wrap into at most `max_lines` lines of at most
    `max_chars_per_line` characters, truncating with an ellipsis if the
    caption doesn't fit -- the on-video overlay is a short hook, not
    necessarily the whole caption (see module docstring)."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    i = 0
    while i < len(words) and len(lines) < max_lines:
        word = words[i]
        candidate = " ".join([*current, word])
        if len(candidate) <= max_chars_per_line or not current:
            current.append(word)
            i += 1
        else:
            lines.append(" ".join(current))
            current = []
    if current and len(lines) < max_lines:
        lines.append(" ".join(current))
        if i >= len(words):
            i = len(words)

    truncated = i < len(words)
    if truncated and lines:
        last = lines[-1]
        if len(last) >= max_chars_per_line:
            last = last[: max_chars_per_line - 1].rstrip()
        lines[-1] = last + "…"

    return "\n".join(lines)


def build_overlay_filter(*, video_height: int, textfile_path: Path) -> str:
    fontsize = max(int(video_height * settings.CAPTION_FONT_SIZE_RATIO), 18)
    box_border = max(int(fontsize * 0.4), 8)
    return (
        f"drawtext=fontfile='{settings.CAPTION_FONT_PATH}'"
        f":textfile='{textfile_path.as_posix()}'"
        f":fontsize={fontsize}"
        f":fontcolor=white"
        f":box=1:boxcolor=black@0.55:boxborderw={box_border}"
        f":line_spacing={int(fontsize * 0.25)}"
        f":x=(w-text_w)/2"
        f":y=h*0.10"  # upper third -- stays clear of Instagram's own UI chrome at the bottom
    )


def burn_caption(input_path: Path, output_path: Path, *, caption_text: str, probe: ProbeResult) -> None:
    """Produces `output_path`: `input_path` with the caption burned in. Video
    is re-encoded (drawtext requires it); audio is copied unchanged."""
    wrapped = wrap_caption_text(
        caption_text, max_chars_per_line=settings.CAPTION_MAX_CHARS_PER_LINE, max_lines=settings.CAPTION_MAX_LINES
    )

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(wrapped)
        textfile_path = Path(f.name)

    try:
        filter_str = build_overlay_filter(video_height=probe.height, textfile_path=textfile_path)
        args = [
            "-i", str(input_path),
            "-vf", filter_str,
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
        ]
        run_ffmpeg(args, output_path=output_path)
    finally:
        textfile_path.unlink(missing_ok=True)
