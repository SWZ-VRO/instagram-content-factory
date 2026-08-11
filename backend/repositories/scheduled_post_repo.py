from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.enums import VariantStatus
from backend.models.scheduled_post import ScheduledPost


def existing_dates_for_account_master(db: Session, *, account_id: str, master_id: str) -> list[datetime]:
    """All scheduled_at_utc values currently holding a slot (RESERVED/
    SCHEDULED/PUBLISHED) for this account+master pair. Small, indexed result
    set (bounded by variants-per-master, max ~10) -- cheap to fetch and
    compare in Python rather than fighting cross-dialect date arithmetic in
    SQL (see backend/schedulers/reservation.py)."""
    stmt = select(ScheduledPost.scheduled_at_utc).where(
        ScheduledPost.account_id == account_id,
        ScheduledPost.master_id == master_id,
        ScheduledPost.status.in_(tuple(s.value for s in VariantStatus.consumed_statuses())),
    )
    return list(db.execute(stmt).scalars().all())


def list_for_account(db: Session, account_id: str, *, limit: int = 200, offset: int = 0) -> list[ScheduledPost]:
    stmt = (
        select(ScheduledPost)
        .where(ScheduledPost.account_id == account_id)
        .order_by(ScheduledPost.scheduled_at_utc.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(stmt).scalars().all())
