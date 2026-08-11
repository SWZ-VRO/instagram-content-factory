from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.api.schemas import LogEntryOut
from backend.models.log import LogEntry

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("", response_model=list[LogEntryOut])
def list_logs(
    code: str | None = Query(default=None),
    level: str | None = Query(default=None),
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """§35 Errors page: centralized log of MISSING_CAPTION, INVALID_MEDIA,
    UPLOAD_FAILED, TOKEN_EXPIRED, RATE_LIMIT, ACCOUNT_AUTH_ERROR,
    SCHEDULING_CONFLICT, CONTENT_SHORTAGE, POSSIBLE_DUPLICATE, ..."""
    stmt = select(LogEntry)
    if code is not None:
        stmt = stmt.where(LogEntry.code == code)
    if level is not None:
        stmt = stmt.where(LogEntry.level == level)
    stmt = stmt.order_by(LogEntry.timestamp.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())
