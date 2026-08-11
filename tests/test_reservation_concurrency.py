"""
§48 Test 7: two workers race to reserve the same variant for two different
accounts at (as close to) the same instant. Exactly one must win; the other
must be refused with a ReservationError. This is the test that actually
proves the DB-level guarantee (partial unique index +
`SELECT ... FOR UPDATE`), not just the sequential app-level check covered
in test_variant_uniqueness.py.
"""
import threading

from backend.core.database import SessionLocal
from backend.models.enums import ScheduledPostStatus
from backend.schedulers.exceptions import ReservationError
from backend.schedulers.reservation import reserve_variant
from tests.factories import make_account, make_master, make_variant

from datetime import datetime, timezone

DAY0 = datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)


def test_test7_concurrent_reservation_only_one_winner(db):
    master = make_master(db)
    variant = make_variant(db, master, index=1)
    ig1 = make_account(db, username="ig001")
    ig2 = make_account(db, username="ig002")
    variant_id, ig1_id, ig2_id = variant.id, ig1.id, ig2.id

    results: dict[str, object] = {}
    start_barrier = threading.Barrier(2)

    def worker(name: str, account_id: str) -> None:
        session = SessionLocal()
        try:
            start_barrier.wait(timeout=5)
            try:
                post = reserve_variant(session, variant_id=variant_id, account_id=account_id, scheduled_at_utc=DAY0)
                results[name] = ("ok", post.id)
            except ReservationError as exc:
                results[name] = ("refused", type(exc).__name__)
        finally:
            session.close()

    t1 = threading.Thread(target=worker, args=("t1", ig1_id))
    t2 = threading.Thread(target=worker, args=("t2", ig2_id))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    outcomes = [results["t1"][0], results["t2"][0]]
    assert outcomes.count("ok") == 1, f"expected exactly one winner, got: {results}"
    assert outcomes.count("refused") == 1, f"expected exactly one refusal, got: {results}"

    # And the database agrees: exactly one consumed scheduled_posts row for this variant.
    verify_session = SessionLocal()
    try:
        from backend.models.scheduled_post import ScheduledPost
        from sqlalchemy import select

        rows = verify_session.execute(
            select(ScheduledPost).where(
                ScheduledPost.variant_id == variant_id,
                ScheduledPost.status.in_(
                    [ScheduledPostStatus.RESERVED, ScheduledPostStatus.SCHEDULED, ScheduledPostStatus.PUBLISHED]
                ),
            )
        ).scalars().all()
        assert len(rows) == 1
    finally:
        verify_session.close()


def test_many_concurrent_reservations_across_distinct_variants_all_succeed(db):
    """Sanity check that the locking above doesn't over-serialize unrelated
    reservations: 10 workers, 10 distinct variants of the same master,
    10 distinct accounts, spaced far enough apart in time to not trip the
    master cooldown -- all 10 must succeed."""
    from datetime import timedelta

    master = make_master(db)
    variants = [make_variant(db, master, index=i) for i in range(1, 11)]
    accounts = [make_account(db, username=f"ig_conc_{i}") for i in range(1, 11)]

    results: dict[int, str] = {}
    start_barrier = threading.Barrier(10)

    def worker(i: int, variant_id: str, account_id: str) -> None:
        session = SessionLocal()
        try:
            start_barrier.wait(timeout=5)
            try:
                reserve_variant(
                    session,
                    variant_id=variant_id,
                    account_id=account_id,
                    scheduled_at_utc=DAY0 + timedelta(days=i * 3),
                )
                results[i] = "ok"
            except ReservationError as exc:
                results[i] = f"refused:{type(exc).__name__}"
        finally:
            session.close()

    threads = [
        threading.Thread(target=worker, args=(i, variants[i].id, accounts[i].id)) for i in range(10)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert all(v == "ok" for v in results.values()), results
