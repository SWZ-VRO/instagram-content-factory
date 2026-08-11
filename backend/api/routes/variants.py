from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.api.schemas import VariantOut
from backend.models.enums import VariantStatus
from backend.services import variant_service

router = APIRouter(prefix="/variants", tags=["variants"])


@router.get("", response_model=list[VariantOut])
def list_variants(
    status: VariantStatus | None = Query(default=None),
    master_id: str | None = Query(default=None),
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    return variant_service.list_variants(db, status=status, master_id=master_id, limit=limit, offset=offset)
