"""
30-day calendar generation (§21-27, §37, §49-51): turns "N active accounts,
a ramping daily post cadence, M available variants" into a set of reserved
(account, variant, UTC datetime) slots.

Validation order for every slot follows §24/§56 exactly -- reserve_variant
(backend/schedulers/reservation.py) already enforces checks 1-7; this module
adds checks 8-10 (slot bookkeeping, atomic reservation is reserve_variant's
job). On any failure for a candidate variant: SKIP to the next candidate,
never violate a higher-priority rule to fill a slot.
"""
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.config import settings as app_settings
from backend.models.account import Account
from backend.models.calendar_plan import CalendarPlan
from backend.models.enums import AccountStatus, CalendarPlanStatus, ScheduledPostStatus, VariantStatus
from backend.models.scheduled_post import ScheduledPost
from backend.models.setting import Setting
from backend.models.variant import Variant
from backend.schedulers.exceptions import ReservationError
from backend.schedulers.reservation import reserve_variant

DEFAULT_TIME_SLOTS = ["08:00", "11:00", "14:00", "17:00", "20:00", "23:00"]


class CalendarPlanNotFound(Exception):
    pass


class CalendarPlanNotApprovable(Exception):
    pass


def _posts_for_day(day_number: int, *, account_min: int, account_max: int) -> int:
    """§21 day-bucket cadence (J1-3: 2/day, J4-7: 3/day, J8-30: 3-5/day),
    clamped to the account's own daily_min_posts/daily_max_posts (§16) --
    those act as a hard per-account cap/floor on top of the global ramp,
    reconciling the two spec sections rather than letting one silently
    override the other."""
    if day_number <= 3:
        bucket_min = bucket_max = app_settings.DAY_1_3_POSTS
    elif day_number <= 7:
        bucket_min = bucket_max = app_settings.DAY_4_7_POSTS
    else:
        bucket_min, bucket_max = app_settings.DAY_8_30_MIN_POSTS, app_settings.DAY_8_30_MAX_POSTS

    # Deterministic spread across [bucket_min, bucket_max] rather than
    # random, so a generated plan is reproducible and explainable -- rotate
    # by day number.
    span = max(bucket_max - bucket_min + 1, 1)
    count = bucket_min + ((day_number - 1) % span)

    if account_max and account_max > 0:
        count = min(count, account_max)
    if account_min and account_min > 0:
        count = max(count, account_min)
    return max(count, 0)


def get_time_slots(db: Session) -> list[time]:
    """Configurable time-of-day slots (§22). Backed by the `settings` table
    (key="post_time_slots", JSON list of "HH:MM" strings) so these are
    editable from the dashboard later (Phase 7) without a migration;
    falls back to DEFAULT_TIME_SLOTS."""
    row = db.execute(select(Setting).where(Setting.key == "post_time_slots")).scalar_one_or_none()
    raw = row.value if row is not None else DEFAULT_TIME_SLOTS
    return sorted(time.fromisoformat(s) for s in raw)


def _pick_slot_times(count: int, slots: list[time]) -> list[time]:
    """Spread `count` posts across the day's configured time slots -- evenly
    if count <= len(slots), cycling if more posts are requested than there
    are configured slots."""
    if count <= 0 or not slots:
        return []
    if count <= len(slots):
        step = len(slots) / count
        return [slots[int(i * step)] for i in range(count)]
    return [slots[i % len(slots)] for i in range(count)]


def _to_utc(local_date: date, local_time: time, tz_name: str) -> datetime:
    local_dt = datetime.combine(local_date, local_time, tzinfo=ZoneInfo(tz_name))
    return local_dt.astimezone(dt_timezone.utc)


def _build_candidate_queue(db: Session) -> deque:
    """AVAILABLE variant ids, interleaved round-robin across masters so
    consecutive picks spread usage across different masters instead of
    draining one master's variants first -- reduces avoidable master-cooldown
    conflicts during allocation (variants without a caption never appear
    here -- they're not AVAILABLE, see models/variant.py)."""
    rows = db.execute(
        select(Variant.id, Variant.master_id)
        .where(Variant.status == VariantStatus.AVAILABLE)
        .order_by(Variant.master_id, Variant.variant_code)
    ).all()

    by_master: dict = {}
    for variant_id, master_id in rows:
        by_master.setdefault(master_id, deque()).append(variant_id)

    queues = list(by_master.values())
    interleaved: deque = deque()
    i = 0
    while queues:
        idx = i % len(queues)
        interleaved.append(queues[idx].popleft())
        if not queues[idx]:
            queues.pop(idx)
        else:
            i += 1
    return interleaved


@dataclass
class SlotAttempt:
    account_username: str
    scheduled_at_utc: datetime
    reserved: bool
    reason: str | None = None


@dataclass
class CalendarGenerationResult:
    plan_id: str
    required_posts: int
    available_variants_at_start: int
    reserved_count: int
    shortage: int
    attempts: list[SlotAttempt] = field(default_factory=list)


def generate_calendar_plan(db: Session, *, start_date: date, days: int | None = None) -> CalendarGenerationResult:
    days = days or app_settings.CALENDAR_DAYS
    time_slots = get_time_slots(db)

    accounts = list(
        db.execute(
            select(Account)
            .where(Account.active.is_(True), Account.status == AccountStatus.ACTIVE)
            .order_by(Account.username)
        )
        .scalars()
        .all()
    )

    # §49: required-posts calculation, up front, for the §26 shortage report.
    required_posts = sum(
        _posts_for_day(d, account_min=a.daily_min_posts, account_max=a.daily_max_posts)
        for a in accounts
        for d in range(1, days + 1)
    )
    available_variants_at_start = db.execute(
        select(func.count()).select_from(Variant).where(Variant.status == VariantStatus.AVAILABLE)
    ).scalar_one()

    plan = CalendarPlan(
        status=CalendarPlanStatus.DRAFT,
        params={
            "start_date": start_date.isoformat(),
            "days": days,
            "required_posts": required_posts,
            "available_variants_at_start": available_variants_at_start,
        },
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    candidates = _build_candidate_queue(db)
    reserved_count = 0
    attempts: list[SlotAttempt] = []

    # §27: variants of the same master ARE allowed across different
    # accounts -- nothing here restricts a master to one account; only
    # reserve_variant's own cooldown check (per account+master) constrains
    # repeat use on the *same* account.
    for account in accounts:
        for day_number in range(1, days + 1):
            local_date = start_date + timedelta(days=day_number - 1)
            count = _posts_for_day(day_number, account_min=account.daily_min_posts, account_max=account.daily_max_posts)

            for slot_time in _pick_slot_times(count, time_slots):
                scheduled_at_utc = _to_utc(local_date, slot_time, account.timezone)
                reserved = False
                reason = "no AVAILABLE variants remain" if not candidates else None

                attempts_budget = len(candidates)
                tried = 0
                while candidates and tried < attempts_budget:
                    variant_id = candidates.popleft()
                    tried += 1
                    try:
                        reserve_variant(
                            db,
                            variant_id=variant_id,
                            account_id=account.id,
                            scheduled_at_utc=scheduled_at_utc,
                            calendar_plan_id=plan.id,
                        )
                        reserved = True
                        reserved_count += 1
                        break  # consumed -- do not requeue
                    except ReservationError as exc:
                        reason = str(exc)
                        candidates.append(variant_id)  # may still suit a different slot/account

                attempts.append(
                    SlotAttempt(
                        account_username=account.username,
                        scheduled_at_utc=scheduled_at_utc,
                        reserved=reserved,
                        reason=None if reserved else reason,
                    )
                )

    shortage = max(required_posts - reserved_count, 0)
    plan.params = {**(plan.params or {}), "reserved_count": reserved_count, "shortage": shortage}
    plan.status = CalendarPlanStatus.REVIEW
    db.commit()

    return CalendarGenerationResult(
        plan_id=plan.id,
        required_posts=required_posts,
        available_variants_at_start=available_variants_at_start,
        reserved_count=reserved_count,
        shortage=shortage,
        attempts=attempts,
    )


def approve_calendar_plan(db: Session, plan_id) -> CalendarPlan:
    """§37: only after APPROVE PLAN do reservations become real schedule
    commitments (RESERVED -> SCHEDULED, on both the post and its variant).
    No publishing happens here or as a result of this call -- that's the
    Publishing Worker's job (Phase 5/6), and it only ever acts on SCHEDULED
    posts, never RESERVED/DRAFT ones."""
    plan = db.get(CalendarPlan, plan_id)
    if plan is None:
        raise CalendarPlanNotFound(str(plan_id))
    if plan.status not in (CalendarPlanStatus.DRAFT, CalendarPlanStatus.REVIEW):
        raise CalendarPlanNotApprovable(f"plan is {plan.status.value}, not DRAFT/REVIEW")

    posts = list(
        db.execute(
            select(ScheduledPost).where(
                ScheduledPost.calendar_plan_id == plan.id, ScheduledPost.status == ScheduledPostStatus.RESERVED
            )
        )
        .scalars()
        .all()
    )
    for post in posts:
        post.status = ScheduledPostStatus.SCHEDULED
        variant = db.get(Variant, post.variant_id)
        if variant is not None:
            variant.status = VariantStatus.SCHEDULED

    plan.status = CalendarPlanStatus.APPROVED
    plan.approved_at = datetime.now(dt_timezone.utc)
    db.commit()
    db.refresh(plan)
    return plan
