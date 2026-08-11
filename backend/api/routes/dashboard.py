from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.api.schemas import DashboardSummary
from backend.core.config import settings
from backend.repositories import account_repo, master_repo
from backend.services import variant_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(db: Session = Depends(get_db)):
    variant_counts = variant_service.inventory_counts(db)
    return DashboardSummary(
        accounts_total=account_repo.count(db),
        accounts_active=account_repo.count_active(db),
        masters_total=master_repo.count(db),
        variants_by_status=variant_counts,
        missing_captions=variant_counts.get("MISSING_CAPTION", 0),
        dry_run=settings.DRY_RUN,
    )
