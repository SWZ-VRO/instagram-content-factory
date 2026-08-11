import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.api.schemas import CalendarGenerateRequest, CalendarGenerateResponse, CalendarPlanOut
from backend.models.calendar_plan import CalendarPlan
from backend.repositories.account_repo import count_active
from backend.schedulers import calendar as calendar_scheduler

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.post("/generate", response_model=CalendarGenerateResponse)
def generate_calendar(payload: CalendarGenerateRequest, db: Session = Depends(get_db)):
    """
    §21-27, §37: builds a DRAFT/REVIEW 30-day plan by reserving AVAILABLE
    variants for active accounts, respecting global uniqueness and the
    master cooldown. Reservation is real (rows move to RESERVED) so the
    plan can be reviewed exactly as it will run -- nothing is published as
    a result of this call; that only ever happens after /calendar/approve
    and, even then, only once the Publishing Worker exists (Phase 5/6).
    """
    if count_active(db) == 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="no active accounts to schedule")

    start_date = payload.start_date or (date.today() + timedelta(days=1))
    result = calendar_scheduler.generate_calendar_plan(db, start_date=start_date, days=payload.days)

    return CalendarGenerateResponse(
        plan_id=result.plan_id,
        required_posts=result.required_posts,
        available_variants_at_start=result.available_variants_at_start,
        reserved_count=result.reserved_count,
        shortage=result.shortage,
        content_shortage=result.shortage > 0,
    )


@router.get("/plans", response_model=list[CalendarPlanOut])
def list_plans(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    from sqlalchemy import select

    stmt = select(CalendarPlan).order_by(CalendarPlan.created_at.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


@router.get("/plans/{plan_id}", response_model=CalendarPlanOut)
def get_plan(plan_id: uuid.UUID, db: Session = Depends(get_db)):
    # NOTE: must be uuid.UUID, not str -- see accounts.py's get_account for
    # why (the native Uuid column type needs an actual uuid.UUID object).
    plan = db.get(CalendarPlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="calendar plan not found")
    return plan


@router.post("/approve/{plan_id}", response_model=CalendarPlanOut)
def approve_plan(plan_id: uuid.UUID, db: Session = Depends(get_db)):
    """§37 APPROVE PLAN: RESERVED -> SCHEDULED for every post in the plan.
    This is the last step before the Publishing Worker is allowed to touch
    anything (Phase 5/6) -- still no network calls made here."""
    try:
        return calendar_scheduler.approve_calendar_plan(db, plan_id)
    except calendar_scheduler.CalendarPlanNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="calendar plan not found") from exc
    except calendar_scheduler.CalendarPlanNotApprovable as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
