"""
Test bootstrap. Forces the app onto an isolated SQLite file BEFORE any
`backend.*` module is imported (settings are read once, at import time),
so these tests never touch a real Postgres instance and never depend on
Docker being available.

SQLite is close enough to Postgres for what we're proving here: the partial
unique index (`uq_scheduled_posts_variant_consumed`) is supported by both
dialects (see models/scheduled_post.py), and SQLite's own database-level
write lock gives us genuine cross-thread serialization to exercise the
concurrent-reservation race in test_reservation_concurrency.py. Anything
Postgres-specific (e.g. exact FOR UPDATE SKIP LOCKED contention behavior)
is out of scope for this suite and should be re-verified against a real
Postgres instance before go-live -- see README.
"""
import os
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP_DB = Path(tempfile.gettempdir()) / f"icf_test_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB}"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["CONTENT_ROOT"] = str(Path(tempfile.gettempdir()) / f"icf_test_content_{uuid.uuid4().hex}")
# Never spin up the background filesystem watcher during tests -- it isn't
# needed (video-pipeline tests call scan_and_import directly) and would
# otherwise touch the DB from a second thread outside test control.
os.environ["WATCHER_ENABLED"] = "false"
os.environ["PUBLISHING_WORKER_ENABLED"] = "false"
# Real value is 1s, meant to catch a file mid-copy in production; at that
# speed it would add ~1s per file to every video-pipeline test.
os.environ["FILE_STABILITY_CHECK_SECONDS"] = "0.01"

import pytest  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import backend.models  # noqa: E402,F401 -- registers every table on Base.metadata
from backend.core.database import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_schema():
    """Every test starts from an empty, freshly-migrated schema -- cheap on
    SQLite and keeps tests independent of execution order."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    if _TMP_DB.exists():
        _TMP_DB.unlink()
