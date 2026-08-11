from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.models.enums import ScheduledPostStatus
from backend.models.mixins import TimestampMixin, UUIDPKMixin


class ScheduledPost(UUIDPKMixin, TimestampMixin, Base):
    """
    One (account, variant, when) allocation. This is where both hard rules
    from the spec are enforced at the database level:

    1. GLOBAL VARIANT UNIQUENESS (§2, §15, §56 rule 1-2):
       partial unique index on `variant_id` for rows whose status is one of
       RESERVED/SCHEDULED/PUBLISHED (the "consumed" states). A variant that
       failed definitively, or a post that was cancelled, does not hold the
       slot -- see VariantStatus.consumed_statuses(). Because this is a real
       unique index (not just an application check), two concurrent
       reservations of the same variant can never both succeed, even under
       race conditions (Test 7, §48) -- the loser gets an IntegrityError.

    2. MASTER COOLDOWN (§6, §7, §56 rule 3):
       `master_id` is denormalized here (copied from variant.master_id at
       reservation time) specifically so the cooldown check --
       "has this account published this master in the last N days" -- is a
       single indexed range query on (account_id, master_id, scheduled_at_utc)
       instead of a join through variants for every candidate slot.

    All timestamps are stored in UTC; the account's timezone is applied only
    for display (§22).
    """
    __tablename__ = "scheduled_posts"
    __table_args__ = (
        Index("ix_scheduled_posts_account_master_time", "account_id", "master_id", "scheduled_at_utc"),
        Index("ix_scheduled_posts_account_time", "account_id", "scheduled_at_utc"),
        Index(
            "uq_scheduled_posts_variant_consumed",
            "variant_id",
            unique=True,
            postgresql_where=sql_text("status IN ('RESERVED', 'SCHEDULED', 'PUBLISHED')"),
            sqlite_where=sql_text("status IN ('RESERVED', 'SCHEDULED', 'PUBLISHED')"),
        ),
    )

    variant_id: Mapped[str] = mapped_column(ForeignKey("variants.id", ondelete="RESTRICT"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), nullable=False, index=True)
    master_id: Mapped[str] = mapped_column(ForeignKey("masters.id", ondelete="RESTRICT"), nullable=False, index=True)
    calendar_plan_id: Mapped[str | None] = mapped_column(
        ForeignKey("calendar_plans.id", ondelete="SET NULL"), nullable=True, index=True
    )

    scheduled_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    status: Mapped[ScheduledPostStatus] = mapped_column(
        SAEnum(ScheduledPostStatus, name="scheduled_post_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ScheduledPostStatus.SCHEDULED,
        index=True,
    )

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_post_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    variant: Mapped["Variant"] = relationship(back_populates="scheduled_posts")  # noqa: F821
    account: Mapped["Account"] = relationship(back_populates="scheduled_posts")  # noqa: F821
    master: Mapped["Master"] = relationship()  # noqa: F821
    calendar_plan: Mapped["CalendarPlan | None"] = relationship(back_populates="scheduled_posts")  # noqa: F821
    jobs: Mapped[list["PublishingJob"]] = relationship(back_populates="scheduled_post")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ScheduledPost variant={self.variant_id} account={self.account_id} status={self.status}>"
