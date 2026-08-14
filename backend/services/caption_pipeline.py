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
from dataclasses import dataclass
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

# Every exception _burn_onto_variant can raise, from every step it takes
# (ffmpeg, local disk, and -- in supabase mode -- network I/O both ways).
# httpx.InvalidURL is listed separately from httpx.HTTPError because it does
# NOT inherit from it (confirmed against the installed httpx version) --
# a malformed/legacy `variant.storage_url` would otherwise raise uncaught.
_BURN_EXCEPTIONS = (FFmpegError, FFmpegNotAvailable, StorageError, OSError, httpx.HTTPError, httpx.InvalidURL)


def _log_error(db: Session, *, code: str, message: str) -> None:
    db.add(LogEntry(timestamp=datetime.now(timezone.utc), level="ERROR", code=code, message=message))
    db.commit()


def attach_caption_and_burn(db: Session, *, variant_id, text: str, source: str = "csv") -> Caption:
    """
    Attaches the caption (verbatim, §11), then burns it onto the variant's
    video. Only flips the variant to AVAILABLE, and only updates its
    sha256/storage_url, once the burn has *fully* succeeded -- a caption
    that's stored but failed to render onto the video (or a burn that
    finished re-encoding but then failed to persist anywhere) must not be
    treated as publishable, same spirit as §13 (no caption -> never
    scheduled).

    Correctness notes:
    - `caption_repo.attach()` is called with `flip_status=False`
      specifically so the variant is NEVER visible as AVAILABLE before the
      burn has actually succeeded. An earlier version of this function let
      `attach()` flip status first and "corrected" it back afterward on
      failure -- that left a real window (a multi-second ffmpeg re-encode,
      sometimes plus a Supabase round-trip) during which the scheduler
      (backend/schedulers/calendar.py, backend/schedulers/reservation.py)
      could reserve/schedule the still-uncaptioned variant, and a failed
      burn would then silently orphan that reservation. There must be
      exactly one place status advances to AVAILABLE for a given caption
      attachment, and it must be after burn success.
    - `_burn_onto_variant` returns the new sha256/storage_url rather than
      mutating `variant` directly, and this function only assigns them
      (and commits) after the whole burn succeeds -- if it mutated
      `variant` as it went and a *later* step failed (e.g. the burn
      re-encodes fine but the Supabase re-upload then fails), the
      except-branch commit below would otherwise persist a `sha256` for a
      file that was never actually saved anywhere, corrupting future exact
      duplicate-hash checks (§14) against this variant.
    """
    variant = db.get(Variant, variant_id)
    if variant is None:
        raise ValueError(f"variant {variant_id} not found")

    was_missing_caption = variant.status == VariantStatus.MISSING_CAPTION

    caption = caption_repo.attach(db, variant_id=variant_id, text=text, source=source, flip_status=False)

    if not was_missing_caption:
        # Correction to a variant that already had a caption (and, if
        # overlay was on, already had it burned in) -- re-burning an
        # already-AVAILABLE-or-further-along variant is a deliberate future
        # enhancement, not done implicitly here to avoid silently
        # re-encoding content that may already be reserved/scheduled.
        return caption

    if not settings.CAPTION_OVERLAY_ENABLED:
        # Overlay is off entirely (e.g. no ffmpeg available in this
        # deployment) -- captions are still used as-is for the post's text
        # field, just never drawn onto the video itself.
        variant.status = VariantStatus.AVAILABLE
        db.commit()
        return caption

    try:
        result = _burn_onto_variant(variant, caption_text=text)
    except _BURN_EXCEPTIONS as exc:
        # Nothing to revert -- status was never advanced, so it's still
        # MISSING_CAPTION and was never schedulable in the meantime. Only
        # the caption text itself (already committed by attach() above) persists.
        _log_error(db, code="INVALID_MEDIA", message=f"{variant.variant_code}: caption burn-in failed: {exc}")
        return caption

    variant.sha256 = result.sha256
    if result.storage_url is not None:
        variant.storage_url = result.storage_url
    variant.status = VariantStatus.AVAILABLE
    db.commit()
    return caption


@dataclass
class _BurnResult:
    sha256: str
    storage_url: str | None  # None when STORAGE_BACKEND=local (irrelevant there)


def _burn_onto_variant(variant: Variant, *, caption_text: str) -> _BurnResult:
    """Does the actual burn + persistence, but does NOT mutate `variant` --
    see the correctness note on `attach_caption_and_burn` for why the
    caller applies the result only after this returns successfully."""
    with tempfile.TemporaryDirectory(prefix="icf_burn_") as tmp:
        tmp_dir = Path(tmp)

        local_path = settings.VARIANTS_DIR / variant.filename
        if local_path.is_file():
            # Common case: this runs right after master_import.py generated
            # the file, in the same process -- the local copy it wrote
            # (needed regardless of storage backend, since ffmpeg has to
            # write *somewhere*) is still sitting right there. Skip the
            # round-trip of downloading back the exact bytes we'd otherwise
            # just uploaded moments earlier.
            source_path = local_path
        elif settings.STORAGE_BACKEND == "supabase" and variant.storage_url:
            # No local copy (e.g. this call is happening in a later
            # process/host with no persistent disk -- exactly the case
            # "supabase" storage exists for, see storage.py) -- fetch it.
            source_path = tmp_dir / f"source_{variant.filename}"
            resp = httpx.get(variant.storage_url, timeout=120.0)
            resp.raise_for_status()
            source_path.write_bytes(resp.content)
        else:
            raise OSError(f"variant file not found locally ({local_path}) and no storage_url to fetch it from")

        source_probe = probe(source_path)
        output_path = tmp_dir / f"burned_{variant.filename}"
        caption_overlay.burn_caption(source_path, output_path, caption_text=caption_text, probe=source_probe)

        # Pixel content changed -- the hash must be recomputed. Computed
        # here as a local value; only written onto `variant` by the caller
        # once every fallible step (including the upload/copy below) has
        # actually succeeded.
        new_sha256 = hashing.sha256_of_file(output_path)
        new_storage_url = None
        if settings.STORAGE_BACKEND == "supabase":
            storage = get_storage()
            new_storage_url = storage.upload(output_path, remote_key=f"variants/{variant.variant_code}.mp4")
        else:
            shutil.copy(output_path, settings.VARIANTS_DIR / variant.filename)

        return _BurnResult(sha256=new_sha256, storage_url=new_storage_url)
