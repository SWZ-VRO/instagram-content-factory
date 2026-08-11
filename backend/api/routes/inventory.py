from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.api.schemas import InventoryRowOut
from backend.models.enums import VariantStatus
from backend.services import inventory_service

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("", response_model=list[InventoryRowOut])
def list_inventory(
    status: VariantStatus | None = Query(default=None),
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """§32 Content Inventory: Master | Variant | Caption | Account | Date | Status, filterable by status."""
    rows = inventory_service.list_inventory(db, status=status, limit=limit, offset=offset)
    return [InventoryRowOut(**vars(r)) for r in rows]
