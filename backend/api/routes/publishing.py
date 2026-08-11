from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.api.schemas import PublishingJobOut, PublishingStatusOut
from backend.models.enums import ScheduledPostStatus
from backend.models.scheduled_post import ScheduledPost
from backend.services import publishing_pipeline

router = APIRouter(prefix="/publishing", tags=["publishing"])


@router.get("/status", response_model=PublishingStatusOut)
def publishing_status(db: Session = Depends(get_db)):
    counts = {}
    for s in ScheduledPostStatus:
        counts[s.value] = db.execute(
            select(func.count()).select_from(ScheduledPost).where(ScheduledPost.status == s)
        ).scalar_one()
    return PublishingStatusOut(
        paused=publishing_pipeline.is_globally_paused(db),
        due_now=len(publishing_pipeline.find_due_posts(db)),
        by_status=counts,
    )


@router.get("/jobs", response_model=list[PublishingJobOut])
def list_jobs(limit: int = 200, offset: int = 0, db: Session = Depends(get_db)):
    """§34 Queue page."""
    return publishing_pipeline.list_jobs(db, limit=limit, offset=offset)


@router.post("/start", response_model=dict)
def publishing_start(db: Session = Depends(get_db)):
    """
    Manually trigger one processing cycle right now (§47) -- the same logic
    the background Publishing Worker (§18/§51) runs automatically every
    PUBLISHING_POLL_INTERVAL_SECONDS. Still respects DRY_RUN and the pause
    flag; this does not bypass either.
    """
    return publishing_pipeline.process_due_posts(db)


@router.post("/pause", response_model=dict)
def publishing_pause(db: Session = Depends(get_db)):
    """§38 PAUSE ALL PUBLISHING."""
    publishing_pipeline.set_globally_paused(db, True)
    return {"paused": True}


@router.post("/resume", response_model=dict)
def publishing_resume(db: Session = Depends(get_db)):
    publishing_pipeline.set_globally_paused(db, False)
    return {"paused": False}
