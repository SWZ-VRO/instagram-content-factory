"""
Atomic variant reservation -- the mechanism that guarantees the project's
#1 rule (§2, §56): a variant is consumed at most once, globally, ever.

Design (see plan / research notes for why):
  - `SELECT ... FOR UPDATE` on the variant row is the fast path: it makes
    concurrent reservers of the *same* variant queue up instead of racing.
    On SQLite (used in tests) this is a no-op and SQLAlchemy silently drops
    it -- fine, because...
  - the real guarantee is the partial unique index
    `uq_scheduled_posts_variant_consumed` on scheduled_posts.variant_id
    (see models/scheduled_post.py). Even if two processes both read
    "AVAILABLE" before either commits, only one INSERT can win; the loser's
    commit raises IntegrityError, which we translate to
    VariantAlreadyReserved. Nothing about correctness depends on the
    row lock -- it's purely a contention/perf optimization.

Validation order follows §24 exactly (steps 5-9 either raise here or are the
caller's job -- slot/provider availability is a Phase 4/5 concern once the
calendar generator and publisher exist).
"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.account import Account
from backend.models.enums import AccountStatus, ScheduledPostStatus, VariantStatus
from backend.models.scheduled_post import ScheduledPost
from backend.models.variant import Variant
from backend.repositories.scheduled_post_repo import existing_dates_for_account_master
from backend.schedulers.exceptions import (
    AccountNotActiveError,
    MasterCooldownViolation,
    MissingCaptionError,
    VariantAlreadyReserved,
    VariantNotAvailable,
    VariantNotFound,
)


def _violates_master_cooldown(
    proposed: datetime, existing_dates: list[datetime], gap_days: int
) -> bool:
    """§6: same master on the same account needs >= gap_days between uses.
    Compared at day granularity, matching the spec's own worked examples
    (12 Aug -> 13 Aug with gap=2 is forbidden; 12 Aug -> 14 Aug is allowed)."""
    proposed_date = proposed.date()
    for other in existing_dates:
        if abs((proposed_date - other.date()).days) < gap_days:
            return True
    return False


def reserve_variant(
    db: Session,
    *,
    variant_id: str,
    account_id: str,
    scheduled_at_utc: datetime,
    calendar_plan_id: str | None = None,
    gap_days: int | None = None,
    require_caption: bool | None = None,
) -> ScheduledPost:
    """
    Attempt to reserve `variant_id` for `account_id` at `scheduled_at_utc`.
    Raises a ReservationError subclass on any rule violation; returns the
    created ScheduledPost (status=RESERVED) on success.
    """
    gap_days = settings.MIN_MASTER_GAP_DAYS if gap_days is None else gap_days
    require_caption = settings.REQUIRE_CAPTION if require_caption is None else require_caption

    variant = db.execute(
        select(Variant).where(Variant.id == variant_id).with_for_update()
    ).scalar_one_or_none()
    if variant is None:
        raise VariantNotFound(variant_id)

    # §24 check 5 (raised ahead of the generic AVAILABLE check when the
    # reason is specifically a missing caption, so callers/dashboard get the
    # precise §35 error code instead of a generic "not available")
    if require_caption and variant.status == VariantStatus.MISSING_CAPTION:
        raise MissingCaptionError(f"{variant.variant_code} has no caption")

    # §24 checks 1-4: must be AVAILABLE (not RESERVED/SCHEDULED/PUBLISHED/FAILED)
    if variant.status != VariantStatus.AVAILABLE:
        raise VariantNotAvailable(f"{variant.variant_code} is {variant.status.value}, not AVAILABLE")

    # Defensive: an AVAILABLE variant should always have a caption by
    # construction (see repositories/caption_repo.attach), but don't rely on
    # that invariant holding forever -- check again explicitly.
    if require_caption and variant.caption is None:
        raise MissingCaptionError(f"{variant.variant_code} has no caption")

    # §24 check 6
    account = db.get(Account, account_id)
    if account is None or not account.active or account.status != AccountStatus.ACTIVE:
        raise AccountNotActiveError(account_id)

    # §24 check 7 -- master cooldown, keyed on account_id + master_id (§7)
    existing_dates = existing_dates_for_account_master(
        db, account_id=account_id, master_id=variant.master_id
    )
    if _violates_master_cooldown(scheduled_at_utc, existing_dates, gap_days):
        raise MasterCooldownViolation(
            f"master {variant.master_id} on account {account_id} within {gap_days}-day cooldown"
        )

    # §24 check 10 -- atomic reservation. The row lock above serializes
    # concurrent attempts on this exact variant; the partial unique index is
    # the backstop if that ever isn't enough (e.g. no row-lock support).
    post = ScheduledPost(
        variant_id=variant.id,
        account_id=account_id,
        master_id=variant.master_id,
        calendar_plan_id=calendar_plan_id,
        scheduled_at_utc=scheduled_at_utc,
        status=ScheduledPostStatus.RESERVED,
    )
    variant.status = VariantStatus.RESERVED
    db.add(post)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise VariantAlreadyReserved(variant.variant_code) from exc

    db.refresh(post)
    return post


def release_variant(db: Session, scheduled_post: ScheduledPost, *, reason: str = "cancelled") -> None:
    """
    Return a variant to AVAILABLE when its reservation is abandoned before
    publish (e.g. plan rejected, or a pre-publish failure classified as
    recoverable -- §5). Never called for PUBLISHED posts.
    """
    if scheduled_post.status == ScheduledPostStatus.PUBLISHED:
        raise ValueError("cannot release a PUBLISHED scheduled_post")

    variant = db.get(Variant, scheduled_post.variant_id)
    scheduled_post.status = ScheduledPostStatus.CANCELLED
    scheduled_post.error = reason
    if variant is not None:
        variant.status = VariantStatus.AVAILABLE
    db.commit()
