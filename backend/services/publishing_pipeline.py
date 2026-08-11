"""
The Publishing Worker's core logic (§18, §51): find due SCHEDULED posts,
run the §51 checklist, publish via the configured SocialPublisher, and
record the outcome. Plain and synchronous, DB-session-scoped, so it's
directly unit-testable; backend/workers/publishing_worker.py is just the
polling/threading wrapper around `process_due_posts`.

§51 flow this mirrors:
    Find due posts -> check account -> check authorization -> check media
    -> check caption -> check idempotency -> publish -> save provider id
    -> PUBLISHED

§5's recoverable-vs-definitive distinction drives every except branch below
-- see backend/publishers/exceptions.py for the taxonomy.
"""
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.account import Account
from backend.models.enums import AccountStatus, ConnectionStatus, PublishingJobStatus, ScheduledPostStatus, VariantStatus
from backend.models.log import LogEntry
from backend.models.publishing import PublishingEvent, PublishingJob
from backend.models.scheduled_post import ScheduledPost
from backend.models.setting import Setting
from backend.models.variant import Variant
from backend.publishers.base import SocialPublisher
from backend.publishers.exceptions import (
    PublisherAuthError,
    PublisherError,
    PublisherPermanentError,
    PublisherRateLimitError,
    PublisherTemporaryError,
)
from backend.publishers.instagram_official import InstagramOfficialPublisher
from backend.repositories import account_connection_repo
from backend.services.media_service import public_media_url


def is_globally_paused(db: Session) -> bool:
    """§38 PAUSE ALL PUBLISHING, backed by the `settings` table (no
    migration needed to add more runtime toggles later)."""
    row = db.execute(select(Setting).where(Setting.key == "publishing_paused")).scalar_one_or_none()
    return bool(row.value) if row is not None else False


def set_globally_paused(db: Session, paused: bool) -> None:
    row = db.execute(select(Setting).where(Setting.key == "publishing_paused")).scalar_one_or_none()
    if row is None:
        db.add(Setting(key="publishing_paused", value=paused))
    else:
        row.value = paused
    db.commit()


def _idempotency_key(account_id, variant_id, scheduled_at_utc: datetime) -> str:
    """§39: account_id + variant_id + scheduled_at."""
    return f"{account_id}:{variant_id}:{scheduled_at_utc.isoformat()}"


def _get_or_create_job(db: Session, post: ScheduledPost) -> PublishingJob:
    key = _idempotency_key(post.account_id, post.variant_id, post.scheduled_at_utc)
    job = db.execute(select(PublishingJob).where(PublishingJob.idempotency_key == key)).scalar_one_or_none()
    if job is None:
        job = PublishingJob(scheduled_post_id=post.id, idempotency_key=key, status=PublishingJobStatus.QUEUED)
        db.add(job)
        db.commit()
        db.refresh(job)
    return job


def _record_event(db: Session, job: PublishingJob, event_type: str, payload: dict | None = None) -> None:
    db.add(PublishingEvent(job_id=job.id, event_type=event_type, timestamp=datetime.now(timezone.utc), payload=payload))
    db.commit()


def _log_error(db: Session, *, code: str, message: str) -> None:
    db.add(LogEntry(timestamp=datetime.now(timezone.utc), level="ERROR", code=code, message=message))
    db.commit()


def _due_for_retry(job: PublishingJob, now: datetime) -> bool:
    """§46 exponential backoff: doubles per attempt from RETRY_BACKOFF_BASE_SECONDS."""
    if job.attempts == 0:
        return True
    backoff = timedelta(seconds=settings.RETRY_BACKOFF_BASE_SECONDS * (2 ** (job.attempts - 1)))
    return job.updated_at + backoff <= now


def find_due_posts(db: Session, *, now: datetime | None = None, limit: int = 100) -> list[ScheduledPost]:
    now = now or datetime.now(timezone.utc)
    stmt = (
        select(ScheduledPost)
        .where(ScheduledPost.status == ScheduledPostStatus.SCHEDULED, ScheduledPost.scheduled_at_utc <= now)
        .order_by(ScheduledPost.scheduled_at_utc)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def process_one(db: Session, post: ScheduledPost, *, publisher: SocialPublisher, now: datetime | None = None) -> str:
    """Returns a short outcome tag: PUBLISHED | SKIPPED | WAITING | FAILED | RETRYING."""
    now = now or datetime.now(timezone.utc)
    job = _get_or_create_job(db, post)

    if job.status == PublishingJobStatus.PUBLISHED:  # §39/§52 idempotency
        return "SKIPPED"
    if not _due_for_retry(job, now):
        return "WAITING"

    account = db.get(Account, post.account_id)
    variant = db.get(Variant, post.variant_id)

    # §51 checklist -- conditions outside the post's own control SKIP
    # (stay SCHEDULED, no attempt burned, §17 "mises en attente sans être perdues").
    if account is None or not account.active or account.status != AccountStatus.ACTIVE:
        return "SKIPPED"
    if account.connection_status in (ConnectionStatus.TOKEN_EXPIRED, ConnectionStatus.DISCONNECTED, ConnectionStatus.ERROR):
        _log_error(db, code="ACCOUNT_AUTH_ERROR", message=f"{account.username} not connected -- post stays queued")
        return "SKIPPED"
    # Media presence check is storage-backend-aware: in "supabase" mode the
    # file lives in cloud storage (variant.storage_url), not on this host's
    # local disk, which may not even be the same host/container that ran
    # the import (see backend/services/storage.py).
    media_present = (
        bool(variant.storage_url) if settings.STORAGE_BACKEND == "supabase" else (settings.VARIANTS_DIR / variant.filename).is_file()
    ) if variant is not None else False
    if not media_present:
        return _fail(db, post, variant, job, code="INVALID_MEDIA", message="variant file missing")
    if variant.caption is None:
        _log_error(db, code="MISSING_CAPTION", message=f"{variant.variant_code} has no caption -- post stays queued")
        return "SKIPPED"

    token = account_connection_repo.get_decrypted_token(db, account.id)
    if token is None or not account.ig_business_id:
        _log_error(db, code="ACCOUNT_AUTH_ERROR", message=f"{account.username} has no stored token/ig_business_id")
        return "SKIPPED"

    if settings.DRY_RUN:
        # §36: no upload, no publish call, no status change -- proves the
        # pipeline would have acted without ever touching Instagram.
        _record_event(db, job, "dry_run_would_publish", {"variant": variant.variant_code, "account": account.username})
        return "SKIPPED"

    job.status = PublishingJobStatus.UPLOADING
    job.attempts += 1
    db.commit()
    _record_event(db, job, "upload_started")

    try:
        media_url = public_media_url(variant)
        container = publisher.upload_media(
            ig_business_id=account.ig_business_id,
            access_token=token,
            media_url=media_url,
            caption=variant.caption.text,
            dry_run=False,
        )
        _record_event(db, job, "upload_completed", {"container_id": container.container_id})

        finished = False
        for _ in range(settings.CONTAINER_POLL_ATTEMPTS):
            status_code = publisher.get_container_status(container_id=container.container_id, access_token=token)
            if status_code == "FINISHED":
                finished = True
                break
            if status_code == "ERROR":
                raise PublisherPermanentError(f"container {container.container_id} reported ERROR")
            time.sleep(settings.CONTAINER_POLL_INTERVAL_SECONDS)

        if not finished:
            # Not finished within the bounded poll -- legitimate transient
            # state (§18 UPLOADING), retried next cycle, not a failure.
            job.status = PublishingJobStatus.RETRYING
            db.commit()
            return "RETRYING"

        result = publisher.publish_post(
            ig_business_id=account.ig_business_id, access_token=token, container=container, dry_run=False
        )

        post.status = ScheduledPostStatus.PUBLISHED
        post.published_at = now
        post.provider_post_id = result.provider_post_id
        variant.status = VariantStatus.PUBLISHED  # permanently consumed -- §5
        job.status = PublishingJobStatus.PUBLISHED
        db.commit()
        _record_event(db, job, "published", {"provider_post_id": result.provider_post_id})
        return "PUBLISHED"

    except PublisherAuthError as exc:
        account.connection_status = ConnectionStatus.TOKEN_EXPIRED
        job.status = PublishingJobStatus.RETRYING
        job.last_error = str(exc)
        db.commit()
        _log_error(db, code="TOKEN_EXPIRED", message=f"{account.username}: {exc}")
        return "RETRYING"

    except PublisherRateLimitError as exc:
        job.status = PublishingJobStatus.RETRYING
        job.last_error = str(exc)
        db.commit()
        _log_error(db, code="RATE_LIMIT", message=str(exc))
        return "RETRYING"

    except PublisherPermanentError as exc:
        return _fail(db, post, variant, job, code="PUBLISH_FAILED", message=str(exc))

    except (PublisherTemporaryError, PublisherError) as exc:
        if job.attempts >= settings.MAX_PUBLISH_ATTEMPTS:
            return _fail(db, post, variant, job, code="PUBLISH_FAILED", message=str(exc))
        job.status = PublishingJobStatus.RETRYING
        job.last_error = str(exc)
        db.commit()
        _log_error(db, code="UPLOAD_FAILED", message=str(exc))
        return "RETRYING"


def _fail(db: Session, post: ScheduledPost, variant: Variant | None, job: PublishingJob, *, code: str, message: str) -> str:
    """§5 "erreur définitive": FAILED is terminal -- never retried again."""
    post.status = ScheduledPostStatus.FAILED
    post.error = message
    if variant is not None:
        variant.status = VariantStatus.FAILED
    job.status = PublishingJobStatus.FAILED
    job.last_error = message
    db.commit()
    _log_error(db, code=code, message=message)
    return "FAILED"


def list_jobs(db: Session, *, limit: int = 200, offset: int = 0) -> list[dict]:
    """§34 Queue page: job_id, account, master/variant, scheduled_at,
    status, attempts, error -- one row per publishing_jobs entry."""
    from backend.models.account import Account
    from backend.models.variant import Variant

    stmt = (
        select(PublishingJob, ScheduledPost.scheduled_at_utc, Account.username, Variant.variant_code)
        .join(ScheduledPost, ScheduledPost.id == PublishingJob.scheduled_post_id)
        .join(Account, Account.id == ScheduledPost.account_id)
        .join(Variant, Variant.id == ScheduledPost.variant_id)
        .order_by(PublishingJob.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = db.execute(stmt).all()
    return [
        {
            "id": job.id,
            "scheduled_post_id": job.scheduled_post_id,
            "status": job.status.value,
            "attempts": job.attempts,
            "last_error": job.last_error,
            "account_username": username,
            "variant_code": variant_code,
            "scheduled_at_utc": scheduled_at,
        }
        for job, scheduled_at, username, variant_code in rows
    ]


def process_due_posts(db: Session, *, publisher: SocialPublisher | None = None) -> dict[str, int]:
    if is_globally_paused(db):
        return {"PAUSED": 1}
    publisher = publisher or InstagramOfficialPublisher()
    outcomes: dict[str, int] = {}
    for post in find_due_posts(db):
        outcome = process_one(db, post, publisher=publisher)
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return outcomes
