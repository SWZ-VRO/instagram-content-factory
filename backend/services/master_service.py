"""
Read-side helpers for masters used by the API/dashboard. The actual
import/hashing/variant-generation pipeline (§10) lives in
backend/services/master_import.py (Phase 2) -- this module stays
read-only to avoid two competing "how a master gets created" code paths.
"""
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.enums import VariantStatus
from backend.models.master import Master
from backend.models.scheduled_post import ScheduledPost
from backend.models.variant import Variant
from backend.repositories import master_repo


def list_masters(db: Session, *, limit: int = 100, offset: int = 0) -> list[Master]:
    return master_repo.list_masters(db, limit=limit, offset=offset)


@dataclass
class MasterSummary:
    master: Master
    variant_count: int
    available_count: int
    consumed_count: int
    accounts_used: int


def list_masters_with_counts(db: Session, *, limit: int = 100, offset: int = 0) -> list[MasterSummary]:
    """§30 Masters page: Master ID, Created, Variants, Available variants,
    Consumed variants, Accounts used, Status.

    NOTE: 4 count queries per master (N+1) -- fine at the page sizes this
    is paginated to (`limit`, default 100), but worth collapsing into a
    single aggregated query with GROUP BY before this is used at the
    1200+ master scale target from §44."""
    masters = master_repo.list_masters(db, limit=limit, offset=offset)
    consumed = tuple(s.value for s in VariantStatus.consumed_statuses())

    summaries = []
    for master in masters:
        variant_count = db.execute(
            select(func.count()).select_from(Variant).where(Variant.master_id == master.id)
        ).scalar_one()
        available_count = db.execute(
            select(func.count())
            .select_from(Variant)
            .where(Variant.master_id == master.id, Variant.status == VariantStatus.AVAILABLE)
        ).scalar_one()
        consumed_count = db.execute(
            select(func.count())
            .select_from(Variant)
            .where(Variant.master_id == master.id, Variant.status.in_(consumed))
        ).scalar_one()
        accounts_used = db.execute(
            select(func.count(func.distinct(ScheduledPost.account_id))).where(ScheduledPost.master_id == master.id)
        ).scalar_one()
        summaries.append(
            MasterSummary(
                master=master,
                variant_count=variant_count,
                available_count=available_count,
                consumed_count=consumed_count,
                accounts_used=accounts_used,
            )
        )
    return summaries
