from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.api.schemas import CaptionImportResult
from backend.services import caption_service

router = APIRouter(prefix="/captions", tags=["captions"])


@router.post("/import", response_model=CaptionImportResult)
async def import_captions(file: UploadFile, db: Session = Depends(get_db)):
    """CSV import per §12 (master_id,variant_id,caption). TXT-per-variant
    import (§12) is added alongside the Phase 2 watcher, which is where
    filesystem-driven association naturally lives."""
    raw = (await file.read()).decode("utf-8")
    try:
        attached = caption_service.import_captions_csv(db, raw)
        return CaptionImportResult(attached=len(attached))
    except caption_service.CaptionImportError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
