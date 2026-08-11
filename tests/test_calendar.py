"""
30-day calendar generation (§21-27, §37, §48 Test 8).
"""
from datetime import date

import pytest
from sqlalchemy import func, select

from backend.core.config import settings
from backend.models.enums import CalendarPlanStatus, ScheduledPostStatus, VariantStatus
from backend.models.scheduled_post import ScheduledPost
from backend.repositories import variant_repo
from backend.schedulers import calendar as calendar_scheduler
from tests.factories import make_account, make_master, make_variant


def test_required_posts_matches_day_bucket_formula_for_one_account(db):
    make_account(db, username="ig001")
    for _ in range(10):
        master = make_master(db)
        for j in range(1, 11):
            make_variant(db, master, index=j)

    result = calendar_scheduler.generate_calendar_plan(db, start_date=date(2026, 9, 1), days=7)
    # day1-3: 2/day * 3 = 6, day4-7: 3/day * 4 = 12 -> 18 total for 1 account over 7 days
    assert result.required_posts == 18
    assert result.reserved_count == 18
    assert result.shortage == 0


def test_global_uniqueness_holds_across_full_generation(db):
    for i in range(5):
        make_account(db, username=f"ig{i:03d}")
    master = make_master(db)
    for j in range(1, 6):
        make_variant(db, master, index=j)

    calendar_scheduler.generate_calendar_plan(db, start_date=date(2026, 9, 1), days=3)

    dupes = db.execute(
        select(ScheduledPost.variant_id, func.count())
        .where(
            ScheduledPost.status.in_(
                [ScheduledPostStatus.RESERVED, ScheduledPostStatus.SCHEDULED, ScheduledPostStatus.PUBLISHED]
            )
        )
        .group_by(ScheduledPost.variant_id)
        .having(func.count() > 1)
    ).all()
    assert dupes == []


def test_master_cooldown_holds_across_full_generation(db):
    """No account should ever get two posts of the SAME master closer than
    MIN_MASTER_GAP_DAYS apart, even after a full multi-day generation run."""
    account = make_account(db, username="ig001")
    master = make_master(db)
    for j in range(1, 11):
        make_variant(db, master, index=j)

    calendar_scheduler.generate_calendar_plan(db, start_date=date(2026, 9, 1), days=10)

    rows = (
        db.execute(
            select(ScheduledPost.scheduled_at_utc)
            .where(ScheduledPost.account_id == account.id, ScheduledPost.master_id == master.id)
            .order_by(ScheduledPost.scheduled_at_utc)
        )
        .scalars()
        .all()
    )
    for a, b in zip(rows, rows[1:]):
        assert abs((b.date() - a.date()).days) >= settings.MIN_MASTER_GAP_DAYS


def test_content_shortage_is_reported_not_silently_filled(db):
    make_account(db, username="ig001")
    master = make_master(db)
    make_variant(db, master, index=1)

    result = calendar_scheduler.generate_calendar_plan(db, start_date=date(2026, 9, 1), days=7)
    assert result.reserved_count == 1
    assert result.shortage == result.required_posts - 1
    assert result.shortage > 0


def test_missing_caption_variants_are_never_reserved(db):
    make_account(db, username="ig001")
    master = make_master(db)
    make_variant(db, master, index=1, with_caption=False)

    result = calendar_scheduler.generate_calendar_plan(db, start_date=date(2026, 9, 1), days=3)
    assert result.reserved_count == 0
    assert result.shortage == result.required_posts


def test_approve_plan_transitions_reserved_to_scheduled(db):
    make_account(db, username="ig001")
    master = make_master(db)
    for j in range(1, 6):
        make_variant(db, master, index=j)

    result = calendar_scheduler.generate_calendar_plan(db, start_date=date(2026, 9, 1), days=2)
    assert result.reserved_count > 0

    plan = calendar_scheduler.approve_calendar_plan(db, result.plan_id)
    assert plan.status == CalendarPlanStatus.APPROVED
    assert plan.approved_at is not None

    posts = db.execute(select(ScheduledPost).where(ScheduledPost.calendar_plan_id == plan.id)).scalars().all()
    assert posts and all(p.status == ScheduledPostStatus.SCHEDULED for p in posts)

    variants = [variant_repo.get(db, p.variant_id) for p in posts]
    assert all(v.status == VariantStatus.SCHEDULED for v in variants)


def test_approve_plan_twice_is_rejected(db):
    make_account(db, username="ig001")
    master = make_master(db)
    make_variant(db, master, index=1)

    result = calendar_scheduler.generate_calendar_plan(db, start_date=date(2026, 9, 1), days=1)
    calendar_scheduler.approve_calendar_plan(db, result.plan_id)

    with pytest.raises(calendar_scheduler.CalendarPlanNotApprovable):
        calendar_scheduler.approve_calendar_plan(db, result.plan_id)


def test_approve_nonexistent_plan_raises_not_found(db):
    import uuid

    with pytest.raises(calendar_scheduler.CalendarPlanNotFound):
        calendar_scheduler.approve_calendar_plan(db, uuid.uuid4())


def test_test8_100_accounts_30_days_generation_completes(db):
    """§48 Test 8: sanity-check calendar generation at 100-account, 30-day
    scale. Uses a modest content pool (not literally ~12,000 variants --
    unrealistic to fabricate in a unit test) which conveniently also
    exercises the content-shortage path at this scale."""
    for i in range(100):
        make_account(db, username=f"ig{i:03d}")
    for _ in range(20):
        master = make_master(db)
        for j in range(1, 11):
            make_variant(db, master, index=j)  # 200 variants available

    result = calendar_scheduler.generate_calendar_plan(db, start_date=date(2026, 9, 1), days=30)

    assert result.required_posts > 200  # 100 accounts over 30 days easily exceeds a 200-variant pool
    assert result.reserved_count <= 200
    assert result.shortage == result.required_posts - result.reserved_count
    assert len(result.attempts) == result.required_posts

    # And global uniqueness still holds at this scale.
    dupes = db.execute(
        select(ScheduledPost.variant_id, func.count())
        .where(ScheduledPost.status == ScheduledPostStatus.RESERVED)
        .group_by(ScheduledPost.variant_id)
        .having(func.count() > 1)
    ).all()
    assert dupes == []
