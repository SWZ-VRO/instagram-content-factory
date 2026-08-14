"""
Ties caption attachment (repositories/caption_repo.py -- plain DB write,
§11 exact text, never touched) to the burn-in step
(services/caption_overlay.py -- produces the actual publishable file). The
two places captions get attached (master_import.py's TXT auto-association,
caption_service.py's CSV import) both go through `attach_caption_and_burn`
instead of calling caption_repo.attach() directly, so "caption attached"
and "video has the caption burned in and is AVAILABLE" never drift apart.

Works with either storage backend (backend/services/storage.py): in
"supabase" mode, downloads the current file from its storage_url, burns,
re-uploads; in "local" mode, reads/writes content/variants/ directly.
"""
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.caption import Caption
from backend.models.enums import VariantStatus
from backend.models.log import LogEntry
from backend.models.variant import Variant
from backend.repositories import caption_repo
from backend.services import caption_overlay, hashing
from backend.services.ffmpeg_runner import FFmpegError, FFmpegNotAvailable, probe
from backend.services.storage import StorageError, get_storage


def _log_error(db: Session, *, code: str, message: str) -> None:
    db.add(LogEntry(timestamp=datetime.now(timezone.utc), level="ERROR", code=code, message=message))
    db.commit()


def attach_caption_and_burn(db: Session, *, variant_id, text: str, source: str = "csv") -> Caption:
    """
    Attaches the caption (verbatim, §11), then burns it onto the variant's
    video. Only flips the variant to AVAILABLE once the burn actually
    succeeds -- a caption that's stored but failed to render onto the video
    must not be treated as publishable, same spirit as §13 (no caption ->
    never scheduled).
    """
    variant = db.get(Variant, variant_id)
    if variant is None:
        raise ValueError(f"variant {variant_id} not found")

    was_missing_caption = variant.status == VariantStatus.MISSING_CAPTION

    caption = caption_repo.attach(db, variant_id=variant_id, text=text, source=source)

    if not settings.CAPTION_OVERLAY_ENABLED or not was_missing_caption:
        # Overlay disabled, or this is a correction to a variant that
        # already had a caption+burn -- re-burning an already-AVAILABLE (or
        # further along) variant is a deliberate future enhancement, not
        # done implicitly here to avoid silently re-encoding content that
        # may already be reserved/scheduled.
        return caption

    try:
        _burn_onto_variant(variant, caption_text=text)
    except (FFmpegError, FFmpegNotAvailable, StorageError, OSError, httpx.HTTPError) as exc:
        variant.status = VariantStatus.MISSING_CAPTION  # keep it out of the schedulable pool
        db.commit()
        _log_error(db, code="INVALID_MEDIA", message=f"{variant.variant_code}: caption burn-in failed: {exc}")
        return caption

    variant.status = VariantStatus.AVAILABLE
    db.commit()
    return caption


def _burn_onto_variant(variant: Variant, *, caption_text: str) -> None:
    with tempfile.TemporaryDirectory(prefix="icf_burn_") as tmp:
        tmp_dir = Path(tmp)

        if settings.STORAGE_BACKEND == "supabase" and variant.storage_url:
            source_path = tmp_dir / f"source_{variant.filename}"
            resp = httpx.get(variant.storage_url, timeout=120.0)
            resp.raise_for_status()
            source_path.write_bytes(resp.content)
        else:
            source_path = settings.VARIANTS_DIR / variant.filename
            if not source_path.is_file():
                raise OSError(f"variant file not found at {source_path}")

        source_probe = probe(source_path)
        output_path = tmp_dir / f"burned_{variant.filename}"
        caption_overlay.burn_caption(source_path, output_path, caption_text=caption_text, probe=source_probe)

        # Replace the servable file with the captioned version -- pixel
        # content changed, so the hash must be recomputed.
        variant.sha256 = hashing.sha256_of_file(output_path)
        if settings.STORAGE_BACKEND == "supabase":
            storage = get_storage()
            variant.storage_url = storage.upload(output_path, remote_key=f"variants/{variant.variant_code}.mp4")
        else:
            shutil.copy(output_path, settings.VARIANTS_DIR / variant.filename)
