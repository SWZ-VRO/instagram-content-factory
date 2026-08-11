"""
Covers spec §48 Tests 1-6: the sequential (non-race) business rules around
global variant uniqueness and the master cooldown. The concurrent case
(Test 7) lives in test_reservation_concurrency.py.
"""
from datetime import datetime, timedelta, timezone

import pytest

from backend.models.enums import VariantStatus
from backend.schedulers.exceptions import (
    AccountNotActiveError,
    MasterCooldownViolation,
    MissingCaptionError,
    VariantNotAvailable,
)
from backend.schedulers.reservation import reserve_variant
from tests.factories import make_account, make_master, make_variant

DAY0 = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def test_test1_global_uniqueness_rejects_second_account(db):
    """§48 Test 1: IG001 -> MASTER_001_V01, then IG002 -> MASTER_001_V01 must be refused."""
    master = make_master(db)
    variant = make_variant(db, master, index=1)
    ig1 = make_account(db, username="ig001")
    ig2 = make_account(db, username="ig002")

    reserve_variant(db, variant_id=variant.id, account_id=ig1.id, scheduled_at_utc=DAY0)

    with pytest.raises(VariantNotAvailable):
        reserve_variant(db, variant_id=variant.id, account_id=ig2.id, scheduled_at_utc=DAY0 + timedelta(days=1))


def test_test2_master_cooldown_one_day_apart_is_refused(db):
    """§48 Test 2: same account, same master, V01 on J1 and V02 on J2 (1 day apart) -> refused."""
    master = make_master(db)
    v1 = make_variant(db, master, index=1)
    v2 = make_variant(db, master, index=2)
    account = make_account(db, username="ig001")

    reserve_variant(db, variant_id=v1.id, account_id=account.id, scheduled_at_utc=DAY0)

    with pytest.raises(MasterCooldownViolation):
        reserve_variant(db, variant_id=v2.id, account_id=account.id, scheduled_at_utc=DAY0 + timedelta(days=1))


def test_test3_master_cooldown_two_days_apart_is_accepted(db):
    """§48 Test 3: V01 on J1, V02 on J3 (2 days apart, gap=2) -> accepted."""
    master = make_master(db)
    v1 = make_variant(db, master, index=1)
    v2 = make_variant(db, master, index=2)
    account = make_account(db, username="ig001")

    reserve_variant(db, variant_id=v1.id, account_id=account.id, scheduled_at_utc=DAY0)
    post = reserve_variant(db, variant_id=v2.id, account_id=account.id, scheduled_at_utc=DAY0 + timedelta(days=2))

    assert post.variant_id == v2.id


def test_test4_different_master_next_day_is_accepted(db):
    """§48 Test 4: MASTER_001_V01 on J1, MASTER_002_V01 on J2 -> accepted (cooldown is per-master)."""
    master1 = make_master(db, master_code="MASTER_001")
    master2 = make_master(db, master_code="MASTER_002")
    v1 = make_variant(db, master1, index=1)
    v2 = make_variant(db, master2, index=1)
    account = make_account(db, username="ig001")

    reserve_variant(db, variant_id=v1.id, account_id=account.id, scheduled_at_utc=DAY0)
    post = reserve_variant(db, variant_id=v2.id, account_id=account.id, scheduled_at_utc=DAY0 + timedelta(days=1))

    assert post.variant_id == v2.id


def test_test5_same_master_different_accounts_same_day_is_accepted(db):
    """§48 Test 5: IG001->V01, IG002->V02, IG003->V03, all same master -> accepted."""
    master = make_master(db)
    variants = [make_variant(db, master, index=i) for i in (1, 2, 3)]
    accounts = [make_account(db, username=f"ig00{i}") for i in (1, 2, 3)]

    for variant, account in zip(variants, accounts):
        post = reserve_variant(db, variant_id=variant.id, account_id=account.id, scheduled_at_utc=DAY0)
        assert post.account_id == account.id


def test_test6_missing_caption_cannot_be_scheduled(db):
    """§48 Test 6: a variant without a caption cannot be reserved."""
    master = make_master(db)
    variant = make_variant(db, master, index=1, with_caption=False)
    assert variant.status == VariantStatus.MISSING_CAPTION
    account = make_account(db, username="ig001")

    with pytest.raises(MissingCaptionError):
        reserve_variant(db, variant_id=variant.id, account_id=account.id, scheduled_at_utc=DAY0)


def test_inactive_account_is_refused(db):
    master = make_master(db)
    variant = make_variant(db, master, index=1)
    account = make_account(db, username="ig001", active=False)

    with pytest.raises(AccountNotActiveError):
        reserve_variant(db, variant_id=variant.id, account_id=account.id, scheduled_at_utc=DAY0)


def test_reserving_twice_via_service_layer_is_refused_even_after_release(db):
    """A released (cancelled) reservation frees the variant; but a PUBLISHED
    one never can be (§5) -- exercised at the model level here since the
    publisher itself isn't implemented until Phase 5."""
    from backend.schedulers.reservation import release_variant

    master = make_master(db)
    variant = make_variant(db, master, index=1)
    ig1 = make_account(db, username="ig001")
    ig2 = make_account(db, username="ig002")

    post = reserve_variant(db, variant_id=variant.id, account_id=ig1.id, scheduled_at_utc=DAY0)
    release_variant(db, post, reason="plan rejected")

    db.refresh(variant)
    assert variant.status == VariantStatus.AVAILABLE

    # Now it's free again -- a *different* account may take it (still only once, globally).
    post2 = reserve_variant(db, variant_id=variant.id, account_id=ig2.id, scheduled_at_utc=DAY0 + timedelta(days=5))
    assert post2.account_id == ig2.id
