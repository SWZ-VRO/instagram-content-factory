"""
Read-side helpers for variants (list/counts) used by the dashboard and
Content Inventory page. Generation (FFmpeg transforms, §8-9) is Phase 2.
"""
from sqlalchemy.orm import Session

from backend.models.enums import VariantStatus
from backend.models.variant import Variant
from backend.repositories import variant_repo


def list_variants(
    db: Session, *, status: VariantStatus | None = None, master_id: str | None = None, limit: int = 100, offset: int = 0
) -> list[Variant]:
    return variant_repo.list_variants(db, status=status, master_id=master_id, limit=limit, offset=offset)


def inventory_counts(db: Session) -> dict[str, int]:
    """Powers the dashboard's Available/Reserved/Scheduled/Published/Failed
    tiles (§25, §28)."""
    return variant_repo.counts_by_status(db)
