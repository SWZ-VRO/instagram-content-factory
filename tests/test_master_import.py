"""
End-to-end tests for the master ingestion pipeline (§10) exercised through
backend/services/master_import.scan_and_import. ffmpeg/ffprobe are faked
(this repo was developed without the real binary installed -- see README
"Tests"); everything else -- file movement between content/ subfolders,
DB writes, duplicate detection, caption auto-association, the MIN_VARIANTS
floor -- runs for real.
"""
import pytest

from backend.core.config import settings
from backend.models.enums import MasterStatus, VariantStatus
from backend.repositories import master_repo, variant_repo
from backend.services import hashing, qc
from backend.services import master_import
from backend.services.ffmpeg_runner import FFmpegError, ProbeResult

FAKE_PROBE = ProbeResult(duration_seconds=10.0, width=1920, height=1080, has_video_stream=True, has_audio_stream=True)


@pytest.fixture(autouse=True)
def _content_dirs(tmp_path, monkeypatch):
    """Redirect the whole content/ tree to a throwaway tmp_path per test."""
    monkeypatch.setattr(settings, "CONTENT_ROOT", tmp_path)
    for sub in ("masters", "processing", "variants", "captions", "ready", "failed", "archive"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture(autouse=True)
def _fake_ffmpeg(monkeypatch):
    """Deterministic stand-ins for the real ffmpeg/ffprobe calls."""

    def fake_probe(path):
        return FAKE_PROBE

    def fake_run_ffmpeg(args, *, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Content depends on the output path so each fake variant gets a
        # distinct SHA256 -- otherwise every "variant" would collide as an
        # exact duplicate of the first.
        output_path.write_bytes(f"FAKE_VARIANT::{output_path.name}".encode())

    monkeypatch.setattr(qc.ffmpeg_runner, "probe", fake_probe)
    monkeypatch.setattr("backend.services.variant_generator.run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(hashing, "perceptual_hash_of_video", lambda path, duration_seconds: None)
    yield


def _drop_master(name: str, content: bytes = b"fake master bytes") -> None:
    (settings.MASTERS_DIR / name).write_bytes(content)


def test_happy_path_creates_master_and_max_variants(db):
    _drop_master("MASTER_777.mp4")
    summary = master_import.scan_and_import(db)

    assert summary.ready_count == 1
    outcome = summary.processed[0]
    assert outcome.master_code == "MASTER_777"
    assert outcome.status == "READY"
    assert outcome.variants_created == settings.MAX_VARIANTS

    master = master_repo.get_by_code(db, "MASTER_777")
    assert master.status == MasterStatus.READY
    # original file moved out of masters/ into archive/, never left in place
    assert not (settings.MASTERS_DIR / "MASTER_777.mp4").exists()
    assert (settings.ARCHIVE_DIR / "MASTER_777.mp4").exists()

    variants = variant_repo.list_variants(db, master_id=master.id, limit=50)
    assert len(variants) == settings.MAX_VARIANTS
    assert all(v.status == VariantStatus.MISSING_CAPTION for v in variants)  # no captions dropped in this test
    assert all((settings.VARIANTS_DIR / v.filename).exists() for v in variants)


def test_auto_derives_sequential_code_for_non_master_named_files(db):
    _drop_master("my_comfyui_export.mp4")
    summary = master_import.scan_and_import(db)
    assert summary.processed[0].master_code == "MASTER_001"


def test_caption_txt_is_auto_associated_and_flips_status_available(db):
    _drop_master("MASTER_010.mp4")
    (settings.CAPTIONS_DIR / "MASTER_010_V01.txt").write_text("Exactly this caption, unmodified.", encoding="utf-8")

    master_import.scan_and_import(db)

    master = master_repo.get_by_code(db, "MASTER_010")
    v01 = next(v for v in variant_repo.list_variants(db, master_id=master.id, limit=50) if v.variant_code == "MASTER_010_V01")
    assert v01.status == VariantStatus.AVAILABLE
    assert v01.caption.text == "Exactly this caption, unmodified."

    v02 = next(v for v in variant_repo.list_variants(db, master_id=master.id, limit=50) if v.variant_code == "MASTER_010_V02")
    assert v02.status == VariantStatus.MISSING_CAPTION


def test_empty_file_is_quarantined_to_failed_not_imported(db):
    (settings.MASTERS_DIR / "MASTER_020.mp4").touch()  # 0 bytes
    summary = master_import.scan_and_import(db)

    assert summary.ready_count == 0
    assert summary.processed[0].status == "FAILED"
    assert master_repo.get_by_code(db, "MASTER_020") is None
    assert (settings.FAILED_DIR / "MASTER_020.mp4").exists()
    assert not (settings.MASTERS_DIR / "MASTER_020.mp4").exists()


def test_exact_duplicate_master_is_rejected_by_content_not_name(db):
    """§14: a rename must never bypass duplicate detection."""
    _drop_master("MASTER_030.mp4", content=b"identical bytes")
    master_import.scan_and_import(db)  # first one imports fine

    _drop_master("totally_renamed_copy.mp4", content=b"identical bytes")
    summary = master_import.scan_and_import(db)

    outcome = [o for o in summary.processed if o.master_code != "MASTER_030"][0]
    assert outcome.status == "DUPLICATE"
    assert (settings.FAILED_DIR / "totally_renamed_copy.mp4").exists()
    # only one master row exists despite two files being dropped
    assert master_repo.count(db) == 1


def test_insufficient_variants_fails_master_and_creates_no_variant_rows(db, monkeypatch):
    """If fewer than MIN_VARIANTS transforms succeed, the master fails
    outright rather than being scheduled with too little content."""
    call_count = {"n": 0}

    def flaky_run_ffmpeg(args, *, output_path):
        call_count["n"] += 1
        if call_count["n"] > 3:  # only the first 3 transforms "succeed"
            raise FFmpegError("simulated encoder failure")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(f"FAKE::{output_path.name}".encode())

    monkeypatch.setattr("backend.services.variant_generator.run_ffmpeg", flaky_run_ffmpeg)

    _drop_master("MASTER_040.mp4")
    summary = master_import.scan_and_import(db)

    assert summary.ready_count == 0
    outcome = summary.processed[0]
    assert outcome.status == "FAILED"
    assert "3/5" in outcome.reasons[0] or "required variants" in outcome.reasons[0]

    master = master_repo.get_by_code(db, "MASTER_040")
    assert master.status == MasterStatus.FAILED
    assert variant_repo.list_variants(db, master_id=master.id, limit=50) == []


def test_near_duplicate_master_is_flagged_not_blocked(db, monkeypatch):
    """§14: perceptual near-duplicates are detected and logged for review,
    but never silently rejected (only exact-hash duplicates are hard-blocked)."""
    from sqlalchemy import select

    from backend.models.log import LogEntry

    # Both masters "hash" to the same value -- content bytes still differ so
    # the exact-sha256 duplicate check does NOT trigger.
    monkeypatch.setattr(hashing, "perceptual_hash_of_video", lambda path, duration_seconds: "00000000f0f0f0f0")

    _drop_master("MASTER_050.mp4", content=b"content A")
    master_import.scan_and_import(db)

    _drop_master("MASTER_051.mp4", content=b"content B")
    summary = master_import.scan_and_import(db)

    # Both imported successfully -- near-duplicate is a warning, not a block.
    assert summary.ready_count == 1
    assert master_repo.count(db) == 2

    logs = db.execute(select(LogEntry).where(LogEntry.code == "POSSIBLE_DUPLICATE")).scalars().all()
    assert len(logs) == 1
    assert "MASTER_050" in logs[0].message


def test_non_video_files_in_masters_dir_are_ignored(db):
    (settings.MASTERS_DIR / "notes.txt").write_text("not a video")
    summary = master_import.scan_and_import(db)
    assert summary.processed == []


def test_supabase_storage_backend_sets_variant_storage_url(db, monkeypatch):
    """When STORAGE_BACKEND=supabase, every created variant must carry a
    permanent public storage_url -- that's what the publishing pipeline
    hands to Instagram instead of a local-disk-only URL."""
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "supabase")
    monkeypatch.setattr(
        "backend.services.master_import.get_storage",
        lambda: type(
            "FakeStorage", (), {"upload": staticmethod(lambda path, remote_key: f"https://fake.supabase.co/{remote_key}")}
        )(),
    )

    _drop_master("MASTER_080.mp4")
    summary = master_import.scan_and_import(db)

    assert summary.ready_count == 1
    master = master_repo.get_by_code(db, "MASTER_080")
    variants = variant_repo.list_variants(db, master_id=master.id, limit=50)
    assert len(variants) == settings.MAX_VARIANTS
    assert all(v.storage_url == f"https://fake.supabase.co/variants/{v.variant_code}.mp4" for v in variants)


def test_supabase_upload_failure_skips_that_variant_only(db, monkeypatch):
    from backend.services.storage import StorageError

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "supabase")

    call_count = {"n": 0}

    def flaky_upload(path, remote_key):
        call_count["n"] += 1
        if call_count["n"] <= 2:
            raise StorageError("simulated upload failure")
        return f"https://fake.supabase.co/{remote_key}"

    monkeypatch.setattr(
        "backend.services.master_import.get_storage",
        lambda: type("FakeStorage", (), {"upload": staticmethod(flaky_upload)})(),
    )

    _drop_master("MASTER_081.mp4")
    summary = master_import.scan_and_import(db)

    # 2 of 10 fail to upload -- still well above MIN_VARIANTS, so the master succeeds overall.
    assert summary.processed[0].status == "READY"
    assert summary.processed[0].variants_created == settings.MAX_VARIANTS - 2


def test_still_being_written_file_is_skipped_not_quarantined(db, monkeypatch):
    """A file that fails the size-stability check must be left alone --
    not imported, not quarantined -- so a future scan can pick it up once
    the copy finishes."""
    _drop_master("MASTER_060.mp4")
    monkeypatch.setattr(master_import, "_is_file_stable", lambda path, check_interval: False)

    summary = master_import.scan_and_import(db)
    assert summary.processed[0].status == "SKIPPED"
    assert (settings.MASTERS_DIR / "MASTER_060.mp4").exists()  # left in place
    assert master_repo.count(db) == 0
