from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.models.enums import PublishingJobStatus
from backend.models.mixins import TimestampMixin, UUIDPKMixin


class PublishingJob(UUIDPKMixin, TimestampMixin, Base):
    """
    The unit of work the Publishing Worker (§18, §51) picks up. Separate from
    ScheduledPost so retries/attempts have their own lifecycle without
    mutating the scheduling record itself.

    `idempotency_key` (§39) = f"{account_id}:{variant_id}:{scheduled_at_utc.isoformat()}"
    is unique -- the worker upserts on this key before ever calling the
    publisher, so a crash/restart mid-publish can never fire the same post
    twice (§52).
    """
    __tablename__ = "publishing_jobs"

    scheduled_post_id: Mapped[str] = mapped_column(
        ForeignKey("scheduled_posts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)

    status: Mapped[PublishingJobStatus] = mapped_column(
        SAEnum(PublishingJobStatus, name="publishing_job_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=PublishingJobStatus.QUEUED,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    scheduled_post: Mapped["ScheduledPost"] = relationship(back_populates="jobs")  # noqa: F821
    events: Mapped[list["PublishingEvent"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class PublishingEvent(UUIDPKMixin, Base):
    """
    Append-only audit trail (§45): created / queued / upload_started /
    upload_completed / scheduled / published / failed, each with a
    timestamp and (sanitized) provider response. Never store tokens here.
    """
    __tablename__ = "publishing_events"

    job_id: Mapped[str] = mapped_column(ForeignKey("publishing_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    job: Mapped["PublishingJob"] = relationship(back_populates="events")
