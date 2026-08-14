"""
Full master ingestion pipeline (§10): detect -> verify integrity -> create
master row -> generate variants -> hash -> match captions -> QC -> archive.
Both the background watcher (backend/workers/watcher.py) and the manual
"IMPORT NOW" endpoint (POST /masters/import) call `scan_and_import`.

Every step that can fail for one file is caught and turned into a
MasterImportOutcome rather than propagating -- one bad drop must never
abort the rest of the batch (§10, general resilience principle in §52).
"""
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.enums import MasterStatus
from backend.models.log import LogEntry
from backend.models.master import Master
from backend.repositories import master_repo, variant_repo
from backend.services import caption_pipeline, hashing, qc
from backend.services.storage import StorageError, get_storage
from backend.services.variant_generator import generate_variants
from backend.validators.content import is_supported_video_file


@dataclass
class MasterImportOutcome:
    master_code: str
    status: str  # "READY" | "FAILED" | "DUPLICATE"
    variants_created: int = 0
    reasons: list[str] = field(default_factory=list)


@dataclass
class ImportSummary:
    processed: list[MasterImportOutcome] = field(default_factory=list)

    @property
    def ready_count(self) -> int:
        return sum(1 for o in self.processed if o.status == "READY")


def _quarantine(path: Path, reason: str) -> None:
    settings.FAILED_DIR.mkdir(parents=True, exist_ok=True)
    destination = settings.FAILED_DIR / path.name
    if path.exists():
        shutil.move(str(path), str(destination))


def _log(db: Session, *, level: str, code: str, message: str) -> None:
    db.add(LogEntry(timestamp=datetime.now(timezone.utc), level=level, code=code, message=message))
    db.commit()


def _find_caption_text(variant_code: str) -> str | None:
    """TXT-per-variant association (§12): content/captions/{variant_code}.txt"""
    caption_file = settings.CAPTIONS_DIR / f"{variant_code}.txt"
    if caption_file.exists():
        return caption_file.read_text(encoding="utf-8").rstrip("\n")
    return None


def _is_file_stable(path: Path, *, check_interval: float) -> bool:
    """A file mid-copy into content/masters/ must never be imported (§10
    step 2). Two size checks `check_interval` seconds apart must agree --
    if the OS is still writing it, the size will have grown in between.
    Note: a genuinely empty (0-byte) file IS "stable" by this definition --
    it just also fails the integrity check right after, which is the
    correct place to reject it (as FAILED, not silently skipped forever)."""
    try:
        size_before = path.stat().st_size
    except OSError:
        return False
    time.sleep(check_interval)
    try:
        size_after = path.stat().st_size
    except OSError:
        return False
    return size_before == size_after


def _derive_master_code(db: Session, filepath: Path) -> str:
    stem_upper = filepath.stem.upper()
    if stem_upper.startswith("MASTER") and master_repo.get_by_code(db, stem_upper) is None:
        return stem_upper
    return master_repo.next_master_code(db)


def _find_near_duplicate_master(db: Session, perceptual_hash: str) -> Master | None:
    for candidate in master_repo.get_with_phash(db):
        if hashing.hamming_distance(perceptual_hash, candidate.perceptual_hash) <= settings.PHASH_DUPLICATE_THRESHOLD:
            return candidate
    return None


def import_one_master(db: Session, master_filepath: Path) -> MasterImportOutcome:
    master_code = _derive_master_code(db, master_filepath)

    # Step 2 (§10): verify integrity BEFORE touching the DB or moving the file.
    integrity = qc.check_master_integrity(master_filepath)
    if not integrity.passed:
        _quarantine(master_filepath, "; ".join(integrity.reasons))
        return MasterImportOutcome(master_code=master_code, status="FAILED", reasons=integrity.reasons)

    sha256 = hashing.sha256_of_file(master_filepath)
    existing = master_repo.get_by_sha256(db, sha256)
    if existing is not None:
        _quarantine(master_filepath, f"duplicate of {existing.master_code}")
        return MasterImportOutcome(
            master_code=master_code, status="DUPLICATE", reasons=[f"identical file already imported as {existing.master_code}"]
        )

    try:
        perceptual_hash = hashing.perceptual_hash_of_video(master_filepath, duration_seconds=integrity.probe.duration_seconds)
    except Exception:  # noqa: BLE001 -- hashing must never block an otherwise-valid import
        perceptual_hash = None

    near_dupe = _find_near_duplicate_master(db, perceptual_hash) if perceptual_hash else None

    # Step 3: move into processing/ and create the DB row.
    settings.PROCESSING_DIR.mkdir(parents=True, exist_ok=True)
    processing_path = settings.PROCESSING_DIR / master_filepath.name
    shutil.move(str(master_filepath), str(processing_path))

    try:
        master = master_repo.create(
            db,
            master_code=master_code,
            filename=master_filepath.name,
            filepath=str(processing_path),
            sha256=sha256,
            perceptual_hash=perceptual_hash,
            duration_seconds=integrity.probe.duration_seconds,
            status=MasterStatus.PROCESSING,
        )
    except Exception as exc:  # noqa: BLE001 -- e.g. master_code collision
        db.rollback()
        _quarantine(processing_path, str(exc))
        return MasterImportOutcome(master_code=master_code, status="FAILED", reasons=[f"could not create master row: {exc}"])

    if near_dupe is not None:
        _log(
            db,
            level="WARNING",
            code="POSSIBLE_DUPLICATE",
            message=f"{master_code} perceptually resembles {near_dupe.master_code} (not blocked -- flagged for manual review)",
        )

    # Steps 4-7: generate variants, hash each, match captions, create rows.
    # Wrapped broadly -- an unexpected failure here must land the master in
    # FAILED, never leave it stuck at PROCESSING nor abort the whole batch.
    try:
        settings.VARIANTS_DIR.mkdir(parents=True, exist_ok=True)
        gen_result = generate_variants(
            processing_path, integrity.probe, master_code=master_code, output_dir=settings.VARIANTS_DIR
        )

        if len(gen_result.successes) < settings.MIN_VARIANTS:
            master.status = MasterStatus.FAILED
            db.commit()
            return MasterImportOutcome(
                master_code=master_code,
                status="FAILED",
                variants_created=len(gen_result.successes),
                reasons=[
                    f"only {len(gen_result.successes)}/{settings.MIN_VARIANTS} required variants generated",
                    *gen_result.failures,
                ],
            )

        storage = get_storage()
        created = 0
        for gv in gen_result.successes:
            variant_sha = hashing.sha256_of_file(gv.filepath)
            if variant_repo.get_by_sha256(db, variant_sha) is not None:
                gv.filepath.unlink(missing_ok=True)
                continue

            variant_code = f"{master_code}_V{gv.index:02d}"

            # In "supabase" storage mode (hosts with no persistent disk --
            # see backend/services/storage.py), a variant isn't usable
            # unless it actually makes it to permanent storage: fail this
            # one variant rather than create a DB row that could never be
            # published later once the local temp file is gone.
            storage_url: str | None = None
            if settings.STORAGE_BACKEND == "supabase":
                try:
                    storage_url = storage.upload(gv.filepath, remote_key=f"variants/{variant_code}.mp4")
                except StorageError as exc:
                    _log(db, level="ERROR", code="UPLOAD_FAILED", message=f"{variant_code}: {exc}")
                    continue

            variant = variant_repo.create(
                db,
                master_id=master.id,
                variant_code=variant_code,
                filename=gv.filepath.name,
                filepath=str(gv.filepath),
                sha256=variant_sha,
                transform=gv.transform_name,
                duration_seconds=gv.probe.duration_seconds,
            )
            if storage_url:
                variant.storage_url = storage_url

            try:
                variant.perceptual_hash = hashing.perceptual_hash_of_video(
                    gv.filepath, duration_seconds=gv.probe.duration_seconds
                )
            except Exception:  # noqa: BLE001
                pass

            caption_text = _find_caption_text(variant_code)
            if caption_text:
                caption_pipeline.attach_caption_and_burn(db, variant_id=variant.id, text=caption_text, source="txt")

            created += 1

        db.commit()

        if created < settings.MIN_VARIANTS:
            master.status = MasterStatus.FAILED
            db.commit()
            return MasterImportOutcome(
                master_code=master_code,
                status="FAILED",
                variants_created=created,
                reasons=[f"only {created}/{settings.MIN_VARIANTS} unique variants survived duplicate filtering"],
            )

    except Exception as exc:  # noqa: BLE001
        db.rollback()
        master.status = MasterStatus.FAILED
        db.commit()
        return MasterImportOutcome(master_code=master_code, status="FAILED", reasons=[f"unexpected error: {exc}"])

    # Step 8: archive the original master file now that processing succeeded.
    settings.ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = settings.ARCHIVE_DIR / processing_path.name
    shutil.move(str(processing_path), str(archive_path))
    master.filepath = str(archive_path)
    master.status = MasterStatus.READY
    db.commit()

    return MasterImportOutcome(master_code=master_code, status="READY", variants_created=created, reasons=gen_result.failures)


def scan_and_import(db: Session) -> ImportSummary:
    """Entry point for both the watcher and the manual IMPORT NOW endpoint:
    process every video file currently sitting in content/masters/."""
    settings.MASTERS_DIR.mkdir(parents=True, exist_ok=True)
    summary = ImportSummary()

    for path in sorted(settings.MASTERS_DIR.iterdir()):
        if not path.is_file() or not is_supported_video_file(path):
            continue
        if not _is_file_stable(path, check_interval=settings.FILE_STABILITY_CHECK_SECONDS):
            # Still being written (e.g. a large ComfyUI export mid-copy) --
            # leave it for the next scan rather than risk importing a
            # truncated file. Not an error: the watcher polls again shortly,
            # and a manual IMPORT NOW can simply be retried.
            summary.processed.append(MasterImportOutcome(master_code=path.stem, status="SKIPPED", reasons=["file still being written"]))
            continue
        try:
            outcome = import_one_master(db, path)
        except Exception as exc:  # noqa: BLE001 -- one bad file must never kill the batch
            db.rollback()
            _log(db, level="ERROR", code="UPLOAD_FAILED", message=f"unexpected error importing {path.name}: {exc}")
            outcome = MasterImportOutcome(master_code=path.stem, status="FAILED", reasons=[str(exc)])
        summary.processed.append(outcome)

    return summary
