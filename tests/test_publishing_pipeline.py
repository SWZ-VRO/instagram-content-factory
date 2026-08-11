"""
Publishing Worker core logic (§18, §51, §5 recoverable-vs-definitive
failures, §39 idempotency). Uses a FakePublisher (implements
SocialPublisher) so nothing here ever makes a real network call to Meta.
"""
from datetime import datetime, timedelta, timezone

import pytest

from backend.core.config import settings
from backend.models.enums import (
    AccountStatus,
    ConnectionStatus,
    PublishingJobStatus,
    ScheduledPostStatus,
    VariantStatus,
)
from backend.models.scheduled_post import ScheduledPost
from backend.publishers.base import MediaContainer, PublishResult, SocialPublisher
from backend.publishers.exceptions import PublisherAuthError, PublisherPermanentError, PublisherRateLimitError
from backend.repositories import account_connection_repo
from backend.services import publishing_pipeline
from tests.factories import make_account, make_master, make_variant


class FakePublisher(SocialPublisher):
    def __init__(self, *, container_status="FINISHED", upload_exc=None, publish_exc=None):
        self.container_status = container_status
        self.upload_exc = upload_exc
        self.publish_exc = publish_exc
        self.upload_calls = 0
        self.publish_calls = 0

    def connect_account(self, *, authorization_code):
        raise NotImplementedError

    def validate_account(self, *, ig_business_id, access_token):
        return True

    def refresh_connection(self, *, access_token):
        raise NotImplementedError

    def upload_media(self, *, ig_business_id, access_token, media_url, caption, dry_run):
        self.upload_calls += 1
        if self.upload_exc:
            raise self.upload_exc
        return MediaContainer(container_id="FAKE_CONTAINER", status="IN_PROGRESS")

    def get_container_status(self, *, container_id, access_token):
        return self.container_status

    def publish_post(self, *, ig_business_id, access_token, container, dry_run):
        self.publish_calls += 1
        if self.publish_exc:
            raise self.publish_exc
        return PublishResult(provider_post_id="PROVIDER_123", raw_response={"id": "PROVIDER_123"})

    def get_post_status(self, *, provider_post_id, access_token):
        return {}

    def cancel_post(self, *, container_id, access_token):
        return None


@pytest.fixture(autouse=True)
def _content_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CONTENT_ROOT", tmp_path)
    (tmp_path / "variants").mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture(autouse=True)
def _public_base_url(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://example.test")
    yield


def _make_due_post(db, *, connected=True, caption=True, media_file=True):
    account = make_account(db, username="ig_pub_1")
    if connected:
        account.ig_business_id = "17800000000000000"
        account.connection_status = ConnectionStatus.CONNECTED
        db.commit()
        account_connection_repo.store_token(db, account_id=account.id, access_token_plain="plaintext-token", expires_at=None)

    master = make_master(db)
    variant = make_variant(db, master, index=1, with_caption=caption)
    if media_file:
        (settings.VARIANTS_DIR / variant.filename).write_bytes(b"fake video bytes")

    post = ScheduledPost(
        variant_id=variant.id,
        account_id=account.id,
        master_id=master.id,
        scheduled_at_utc=datetime.now(timezone.utc) - timedelta(minutes=1),
        status=ScheduledPostStatus.SCHEDULED,
    )
    variant.status = VariantStatus.SCHEDULED
    db.add(post)
    db.commit()
    db.refresh(post)
    return account, variant, post


def test_dry_run_never_calls_the_publisher(db, monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN", True)
    _account, variant, post = _make_due_post(db)
    publisher = FakePublisher()

    outcome = publishing_pipeline.process_one(db, post, publisher=publisher)

    assert outcome == "SKIPPED"
    assert publisher.upload_calls == 0
    db.refresh(post)
    assert post.status == ScheduledPostStatus.SCHEDULED  # untouched


def test_successful_publish_marks_post_and_variant_published(db, monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN", False)
    _account, variant, post = _make_due_post(db)
    publisher = FakePublisher()

    outcome = publishing_pipeline.process_one(db, post, publisher=publisher)

    assert outcome == "PUBLISHED"
    db.refresh(post)
    db.refresh(variant)
    assert post.status == ScheduledPostStatus.PUBLISHED
    assert post.provider_post_id == "PROVIDER_123"
    assert post.published_at is not None
    assert variant.status == VariantStatus.PUBLISHED  # permanently consumed -- §5


def test_idempotent_reprocessing_of_already_published_job_is_a_noop(db, monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN", False)
    _account, variant, post = _make_due_post(db)
    publisher = FakePublisher()

    publishing_pipeline.process_one(db, post, publisher=publisher)
    assert publisher.upload_calls == 1

    # Re-processing the SAME post (e.g. after a worker restart, §52) must
    # never call the publisher again -- §39 idempotency.
    outcome = publishing_pipeline.process_one(db, post, publisher=publisher)
    assert outcome == "SKIPPED"
    assert publisher.upload_calls == 1


def test_auth_error_marks_account_token_expired_and_keeps_post_queued(db, monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN", False)
    account, variant, post = _make_due_post(db)
    publisher = FakePublisher(upload_exc=PublisherAuthError("token invalid"))

    outcome = publishing_pipeline.process_one(db, post, publisher=publisher)

    assert outcome == "RETRYING"
    db.refresh(account)
    db.refresh(post)
    assert account.connection_status == ConnectionStatus.TOKEN_EXPIRED
    # §17: the post is NOT lost -- it stays queued for when the account is reconnected.
    assert post.status == ScheduledPostStatus.SCHEDULED


def test_permanent_error_fails_post_and_variant_for_good(db, monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN", False)
    _account, variant, post = _make_due_post(db)
    publisher = FakePublisher(publish_exc=PublisherPermanentError("invalid media"))

    outcome = publishing_pipeline.process_one(db, post, publisher=publisher)

    assert outcome == "FAILED"
    db.refresh(post)
    db.refresh(variant)
    assert post.status == ScheduledPostStatus.FAILED
    assert variant.status == VariantStatus.FAILED


def test_rate_limit_is_retried_not_failed(db, monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN", False)
    _account, variant, post = _make_due_post(db)
    publisher = FakePublisher(upload_exc=PublisherRateLimitError("slow down"))

    outcome = publishing_pipeline.process_one(db, post, publisher=publisher)

    assert outcome == "RETRYING"
    db.refresh(post)
    assert post.status == ScheduledPostStatus.SCHEDULED  # not failed, not published


def test_missing_media_file_fails_immediately(db, monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN", False)
    _account, variant, post = _make_due_post(db, media_file=False)
    publisher = FakePublisher()

    outcome = publishing_pipeline.process_one(db, post, publisher=publisher)

    assert outcome == "FAILED"
    assert publisher.upload_calls == 0
    db.refresh(post)
    db.refresh(variant)
    assert post.status == ScheduledPostStatus.FAILED
    assert variant.status == VariantStatus.FAILED


def test_missing_caption_is_skipped_and_left_queued(db, monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN", False)
    _account, variant, post = _make_due_post(db, caption=False)
    publisher = FakePublisher()

    outcome = publishing_pipeline.process_one(db, post, publisher=publisher)

    assert outcome == "SKIPPED"
    assert publisher.upload_calls == 0
    db.refresh(post)
    assert post.status == ScheduledPostStatus.SCHEDULED


def test_disconnected_account_is_skipped_not_failed(db, monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN", False)
    _account, variant, post = _make_due_post(db, connected=False)
    publisher = FakePublisher()

    outcome = publishing_pipeline.process_one(db, post, publisher=publisher)

    assert outcome == "SKIPPED"
    assert publisher.upload_calls == 0
    db.refresh(post)
    assert post.status == ScheduledPostStatus.SCHEDULED


def test_global_pause_short_circuits_before_touching_any_post(db, monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN", False)
    _account, variant, post = _make_due_post(db)
    publishing_pipeline.set_globally_paused(db, True)

    outcomes = publishing_pipeline.process_due_posts(db, publisher=FakePublisher())

    assert outcomes == {"PAUSED": 1}
    db.refresh(post)
    assert post.status == ScheduledPostStatus.SCHEDULED


def test_resume_after_pause_allows_processing_again(db, monkeypatch):
    monkeypatch.setattr(settings, "DRY_RUN", False)
    _account, variant, post = _make_due_post(db)
    publishing_pipeline.set_globally_paused(db, True)
    publishing_pipeline.set_globally_paused(db, False)

    outcomes = publishing_pipeline.process_due_posts(db, publisher=FakePublisher())

    assert outcomes.get("PUBLISHED") == 1
