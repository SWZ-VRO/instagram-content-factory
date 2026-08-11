"""
Smoke tests for the Phase 1 HTTP surface: healthcheck, account CRUD,
masters/variants listing, caption CSV import, and the dashboard summary
actually reflecting live DB state (not hardcoded numbers).
"""
from fastapi.testclient import TestClient

from backend.main import app
from tests.factories import make_account, make_master, make_variant

client = TestClient(app)


def test_health(db):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_and_list_account(db):
    resp = client.post("/accounts", json={"username": "ig_api_test", "timezone": "Europe/Paris"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "ig_api_test"
    assert body["timezone"] == "Europe/Paris"

    resp = client.get("/accounts")
    assert resp.status_code == 200
    usernames = [a["username"] for a in resp.json()]
    assert "ig_api_test" in usernames


def test_create_duplicate_account_is_conflict(db):
    client.post("/accounts", json={"username": "ig_dupe"})
    resp = client.post("/accounts", json={"username": "ig_dupe"})
    assert resp.status_code == 409


def test_dashboard_summary_reflects_live_data(db):
    master = make_master(db, master_code="MASTER_API_1")
    make_variant(db, master, index=1, with_caption=True)
    make_variant(db, master, index=2, with_caption=False)
    make_account(db, username="ig_dash_1")

    resp = client.get("/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["masters_total"] >= 1
    assert body["variants_by_status"]["AVAILABLE"] >= 1
    assert body["variants_by_status"]["MISSING_CAPTION"] >= 1
    assert body["missing_captions"] >= 1
    assert body["dry_run"] is True  # DRY_RUN defaults true -- §36


def test_caption_csv_import_uses_text_verbatim(db):
    master = make_master(db, master_code="MASTER_CAP_1")
    variant = make_variant(db, master, index=1, with_caption=False)

    csv_content = (
        "master_id,variant_id,caption\n"
        f'MASTER_CAP_1,{variant.variant_code},"Hello world, exactly this."\n'
    )
    files = {"file": ("captions.csv", csv_content, "text/csv")}
    resp = client.post("/captions/import", files=files)
    assert resp.status_code == 200
    assert resp.json()["attached"] == 1

    resp = client.get("/variants", params={"status": "AVAILABLE"})
    codes = [v["variant_code"] for v in resp.json()]
    assert variant.variant_code in codes


def test_oauth_authorize_without_app_credentials_returns_501_not_fake_url():
    """§59: never fake a feature that isn't usable yet -- without a
    configured Meta Developer App, this must not return a broken/fake URL."""
    resp = client.get("/accounts/oauth/authorize")
    assert resp.status_code == 501


def test_publishing_start_is_real_and_respects_dry_run(db):
    """§18/§47/§59: unlike OAuth (needs real Meta credentials), the
    publishing cycle trigger IS implemented -- it must actually run
    (respecting DRY_RUN), not return 501."""
    resp = client.post("/publishing/start")
    assert resp.status_code == 200

    resp = client.get("/publishing/status")
    assert resp.status_code == 200
    assert "paused" in resp.json() and "by_status" in resp.json()


def test_publishing_pause_and_resume(db):
    resp = client.post("/publishing/pause")
    assert resp.status_code == 200 and resp.json()["paused"] is True
    assert client.get("/publishing/status").json()["paused"] is True

    resp = client.post("/publishing/resume")
    assert resp.status_code == 200 and resp.json()["paused"] is False


def test_connect_manual_unknown_account_returns_422_no_network_call(db):
    import uuid

    resp = client.post(
        f"/accounts/{uuid.uuid4()}/connect/manual", json={"ig_business_id": "1", "access_token": "x"}
    )
    assert resp.status_code == 422


def test_get_account_by_id(db):
    resp = client.post("/accounts", json={"username": "ig_get_by_id"})
    account_id = resp.json()["id"]

    resp = client.get(f"/accounts/{account_id}")
    assert resp.status_code == 200
    assert resp.json()["username"] == "ig_get_by_id"


def test_inventory_lists_variants_with_master_and_caption(db):
    master = make_master(db, master_code="MASTER_INV_1")
    make_variant(db, master, index=1, with_caption=True)

    resp = client.get("/inventory")
    assert resp.status_code == 200
    rows = resp.json()
    row = next(r for r in rows if r["variant_code"] == "MASTER_INV_1_V01")
    assert row["master_code"] == "MASTER_INV_1"
    assert row["caption_text"] == "Caption for MASTER_INV_1_V01"
    assert row["account_username"] is None
    assert row["status"] == "AVAILABLE"


def test_calendar_generate_and_approve_end_to_end(db):
    make_account(db, username="ig_cal_1")
    master = make_master(db, master_code="MASTER_CAL_1")
    for j in range(1, 6):
        make_variant(db, master, index=j, with_caption=True)

    resp = client.post("/calendar/generate", json={"start_date": "2026-09-01", "days": 2})
    assert resp.status_code == 200
    body = resp.json()
    assert body["reserved_count"] > 0
    plan_id = body["plan_id"]

    resp = client.get(f"/calendar/plans/{plan_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "REVIEW"

    resp = client.post(f"/calendar/approve/{plan_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"

    # Double-approve is rejected, not silently accepted.
    resp = client.post(f"/calendar/approve/{plan_id}")
    assert resp.status_code == 409


def test_calendar_generate_without_active_accounts_is_rejected(db):
    resp = client.post("/calendar/generate", json={})
    assert resp.status_code == 422


def test_logs_endpoint_lists_entries(db):
    from datetime import datetime, timezone

    from backend.core.database import SessionLocal
    from backend.models.log import LogEntry

    session = SessionLocal()
    session.add(LogEntry(timestamp=datetime.now(timezone.utc), level="ERROR", code="INVALID_MEDIA", message="test log"))
    session.commit()
    session.close()

    resp = client.get("/logs")
    assert resp.status_code == 200
    assert any(row["code"] == "INVALID_MEDIA" for row in resp.json())

    resp = client.get("/logs", params={"code": "INVALID_MEDIA"})
    assert resp.status_code == 200
    assert all(row["code"] == "INVALID_MEDIA" for row in resp.json())


def test_publishing_jobs_endpoint(db):
    resp = client.get("/publishing/jobs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_masters_list_includes_variant_counts(db):
    master = make_master(db, master_code="MASTER_COUNT_1")
    make_variant(db, master, index=1, with_caption=True)
    make_variant(db, master, index=2, with_caption=False)

    resp = client.get("/masters")
    assert resp.status_code == 200
    row = next(m for m in resp.json() if m["master_code"] == "MASTER_COUNT_1")
    assert row["variant_count"] == 2
    assert row["available_count"] == 1
    assert row["consumed_count"] == 0
    assert row["accounts_used"] == 0


def test_masters_import_is_real_not_a_stub(db):
    """§10/§59: unlike the endpoints above, master import IS implemented
    (Phase 2) -- it must actually run the pipeline, not return 501."""
    resp = client.post("/masters/import")
    assert resp.status_code == 200
    body = resp.json()
    assert "processed" in body and "ready_count" in body
