"""
Content Inventory (§32): one row per variant, joined with its master,
caption (if any), and — if it currently holds an active reservation — the
account and date it's allocated to. Read-only; a single indexed query, no
N+1 (the ScheduledPost/Account joins are LEFT OUTER and pre-filtered to at
most one "active" row per variant via the same consumed-status set that
backs the global-uniqueness index -- see models/scheduled_post.py).
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.account import Account
from backend.models.caption import Caption
from backend.models.enums import VariantStatus
from backend.models.master import Master
from backend.models.scheduled_post import ScheduledPost
from backend.models.variant import Variant


@dataclass
class InventoryRow:
    master_code: str
    variant_code: str
    caption_text: str | None
    account_username: str | None
    scheduled_at_utc: datetime | None
    status: str


def list_inventory(
    db: Session, *, status: VariantStatus | None = None, limit: int = 200, offset: int = 0
) -> list[InventoryRow]:
    consumed = tuple(s.value for s in VariantStatus.consumed_statuses())

    stmt = (
        select(Variant, Master.master_code, Caption.text, Account.username, ScheduledPost.scheduled_at_utc)
        .join(Master, Master.id == Variant.master_id)
        .outerjoin(Caption, Caption.variant_id == Variant.id)
        .outerjoin(
            ScheduledPost,
            (ScheduledPost.variant_id == Variant.id) & (ScheduledPost.status.in_(consumed)),
        )
        .outerjoin(Account, Account.id == ScheduledPost.account_id)
    )
    if status is not None:
        stmt = stmt.where(Variant.status == status)
    stmt = stmt.order_by(Variant.created_at.desc()).limit(limit).offset(offset)

    rows = db.execute(stmt).all()
    return [
        InventoryRow(
            master_code=master_code,
            variant_code=variant.variant_code,
            caption_text=caption_text,
            account_username=account_username,
            scheduled_at_utc=scheduled_at,
            status=variant.status.value,
        )
        for variant, master_code, caption_text, account_username, scheduled_at in rows
    ]
