"""
backend/services/caption_pipeline.py -- the orchestration that ties caption
attachment to burning the caption onto the video. ffmpeg is mocked (this
repo was developed without the real binary installed -- see README "Tests").
"""
from sqlalchemy import select

import pytest

from backend.core.config import settings
from backend.models.enums import VariantStatus
from backend.models.log import LogEntry
from backend.services import caption_pipeline
from backend.services.ffmpeg_runner import FFmpegError, ProbeResult
from tests.factories import make_account, make_master, make_variant  # noqa: F401 -- account unused here but keeps parity

FAKE_PROBE = ProbeResult(duration_seconds=10.0, width=1080, height=1920, has_video_stream=True, has_audio_stream=True)


@pytest.fixture(autouse=True)
def _content_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CONTENT_ROOT", tmp_path)
    (tmp_path / "variants").mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture(autouse=True)
def _enable_overlay(monkeypatch):
    monkeypatch.setattr(settings, "CAPTION_OVERLAY_ENABLED", True)
    yield


def _make_variant_with_file(db, *, with_caption=False):
    master = make_master(db)
    variant = make_variant(db, master, index=1, with_caption=with_caption)
    (settings.VARIANTS_DIR / variant.filename).write_bytes(b"original variant bytes")
    return variant


def test_successful_burn_marks_variant_available_and_rehashes(db, monkeypatch):
    variant = _make_variant_with_file(db)
    original_sha = variant.sha256

    def fake_probe(path):
        return FAKE_PROBE

    def fake_run_ffmpeg(args, *, output_path):
        output_path.write_bytes(b"burned video bytes -- different content")

    monkeypatch.setattr("backend.services.caption_pipeline.probe", fake_probe)
    monkeypatch.setattr("backend.services.caption_overlay.run_ffmpeg", fake_run_ffmpeg)

    caption = caption_pipeline.attach_caption_and_burn(db, variant_id=variant.id, text="Exactly this caption.", source="txt")

    assert caption.text == "Exactly this caption."  # never reformulated -- §11
    db.refresh(variant)
    assert variant.status == VariantStatus.AVAILABLE
    assert variant.sha256 != original_sha  # pixel content changed -- must re-hash
    assert (settings.VARIANTS_DIR / variant.filename).read_bytes() == b"burned video bytes -- different content"


def test_burn_failure_keeps_variant_missing_caption_and_logs(db, monkeypatch):
    variant = _make_variant_with_file(db)

    def fake_probe(path):
        return FAKE_PROBE

    def failing_run_ffmpeg(args, *, output_path):
        raise FFmpegError("simulated drawtext failure")

    monkeypatch.setattr("backend.services.caption_pipeline.probe", fake_probe)
    monkeypatch.setattr("backend.services.caption_overlay.run_ffmpeg", failing_run_ffmpeg)

    caption = caption_pipeline.attach_caption_and_burn(db, variant_id=variant.id, text="Some caption.", source="txt")

    assert caption.text == "Some caption."  # still stored verbatim, even though burn failed
    db.refresh(variant)
    assert variant.status == VariantStatus.MISSING_CAPTION  # not schedulable until burn succeeds

    logs = db.execute(select(LogEntry).where(LogEntry.code == "INVALID_MEDIA")).scalars().all()
    assert len(logs) == 1
    assert variant.variant_code in logs[0].message


def test_overlay_disabled_skips_burn_but_still_flips_available(db, monkeypatch):
    monkeypatch.setattr(settings, "CAPTION_OVERLAY_ENABLED", False)
    variant = _make_variant_with_file(db)
    original_sha = variant.sha256

    called = {"n": 0}
    monkeypatch.setattr(
        "backend.services.caption_overlay.run_ffmpeg", lambda *a, **k: called.__setitem__("n", called["n"] + 1)
    )

    caption_pipeline.attach_caption_and_burn(db, variant_id=variant.id, text="Caption text.", source="csv")

    db.refresh(variant)
    assert variant.status == VariantStatus.AVAILABLE
    assert variant.sha256 == original_sha  # untouched -- burn never ran
    assert called["n"] == 0


def test_correcting_an_already_available_variants_caption_does_not_reburn(db, monkeypatch):
    variant = _make_variant_with_file(db, with_caption=True)
    assert variant.status == VariantStatus.AVAILABLE

    called = {"n": 0}
    monkeypatch.setattr(
        "backend.services.caption_overlay.run_ffmpeg", lambda *a, **k: called.__setitem__("n", called["n"] + 1)
    )

    caption = caption_pipeline.attach_caption_and_burn(db, variant_id=variant.id, text="Corrected caption.", source="csv")

    assert caption.text == "Corrected caption."
    assert called["n"] == 0  # re-burning an already-published-pipeline-ready variant is not done implicitly


def _make_fake_storage(uploads: list) -> type:
    class FakeStorage:
        def upload(self, path, remote_key):
            uploads.append(remote_key)
            return f"https://fake.supabase.co/storage/v1/object/public/content/{remote_key}"

    return FakeStorage


def test_supabase_backend_downloads_when_no_local_copy_exists(db, monkeypatch):
    """The scenario STORAGE_BACKEND=supabase exists for: no local disk (a
    fresh/ephemeral host), so the file must come from its storage_url."""
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "supabase")
    master = make_master(db)
    variant = make_variant(db, master, index=1, with_caption=False)
    original_url = "https://fake.supabase.co/storage/v1/object/public/content/variants/original.mp4"
    variant.storage_url = original_url
    db.commit()
    assert not (settings.VARIANTS_DIR / variant.filename).exists()  # no local copy -- the case under test

    class FakeResp:
        content = b"downloaded original bytes"

        def raise_for_status(self):
            pass

    get_calls = []
    monkeypatch.setattr(
        "backend.services.caption_pipeline.httpx.get",
        lambda url, timeout: (get_calls.append(url), FakeResp())[1],
    )
    monkeypatch.setattr("backend.services.caption_pipeline.probe", lambda path: FAKE_PROBE)
    monkeypatch.setattr(
        "backend.services.caption_overlay.run_ffmpeg",
        lambda args, *, output_path: output_path.write_bytes(b"burned + reuploaded bytes"),
    )

    uploads: list = []
    monkeypatch.setattr("backend.services.caption_pipeline.get_storage", lambda: _make_fake_storage(uploads)())

    caption_pipeline.attach_caption_and_burn(db, variant_id=variant.id, text="Cloud caption.", source="txt")

    db.refresh(variant)
    assert get_calls == [original_url]  # actually fetched the pre-burn file over the network
    assert variant.status == VariantStatus.AVAILABLE
    assert uploads == [f"variants/{variant.variant_code}.mp4"]
    assert variant.storage_url.endswith(f"variants/{variant.variant_code}.mp4")


def test_supabase_backend_skips_download_when_local_copy_still_present(db, monkeypatch):
    """Right after master_import.py generates+uploads a variant, the local
    copy it wrote (to run ffmpeg against) is still on disk -- burning the
    caption in the same process shouldn't pay for a redundant
    upload-then-immediately-download round trip."""
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "supabase")
    variant = _make_variant_with_file(db)  # writes a local copy
    variant.storage_url = "https://fake.supabase.co/storage/v1/object/public/content/variants/original.mp4"
    db.commit()

    get_calls = []
    monkeypatch.setattr("backend.services.caption_pipeline.httpx.get", lambda url, timeout: get_calls.append(url))
    monkeypatch.setattr("backend.services.caption_pipeline.probe", lambda path: FAKE_PROBE)
    monkeypatch.setattr(
        "backend.services.caption_overlay.run_ffmpeg",
        lambda args, *, output_path: output_path.write_bytes(b"burned bytes"),
    )
    uploads: list = []
    monkeypatch.setattr("backend.services.caption_pipeline.get_storage", lambda: _make_fake_storage(uploads)())

    caption_pipeline.attach_caption_and_burn(db, variant_id=variant.id, text="Cloud caption.", source="txt")

    assert get_calls == []  # never touched the network to fetch what was already local
    db.refresh(variant)
    assert variant.status == VariantStatus.AVAILABLE
