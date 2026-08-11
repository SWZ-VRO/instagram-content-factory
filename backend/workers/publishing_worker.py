"""
Background Publishing Worker (§18, §51): polls for due SCHEDULED posts and
publishes them. Same "daemon thread now, Celery later" pattern as
backend/workers/watcher.py -- see that module's docstring for why polling
(not push/events) and why a thread is an honest stand-in for Phase 6's
Celery worker rather than a shortcut that needs rearchitecting later (the
real logic, backend/services/publishing_pipeline.py, doesn't know or care
how it gets invoked).
"""
import logging
import threading
import time

from backend.core.config import settings
from backend.core.database import SessionLocal
from backend.services.publishing_pipeline import process_due_posts

logger = logging.getLogger("icf.publishing_worker")

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def _run_loop() -> None:
    logger.info("publishing worker started, polling every %.1fs (DRY_RUN=%s)", settings.PUBLISHING_POLL_INTERVAL_SECONDS, settings.DRY_RUN)
    while not _stop_event.is_set():
        try:
            db = SessionLocal()
            try:
                outcomes = process_due_posts(db)
                if outcomes:
                    logger.info("publishing cycle: %s", outcomes)
            finally:
                db.close()
        except Exception:  # noqa: BLE001 -- the loop must survive any single bad cycle (§52)
            logger.exception("publishing cycle failed, will retry next poll")
        _stop_event.wait(settings.PUBLISHING_POLL_INTERVAL_SECONDS)


def start() -> None:
    global _thread
    if not settings.PUBLISHING_WORKER_ENABLED:
        logger.info("publishing worker disabled (PUBLISHING_WORKER_ENABLED=false)")
        return
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_run_loop, name="icf-publishing-worker", daemon=True)
    _thread.start()


def stop() -> None:
    _stop_event.set()
    if _thread is not None:
        _thread.join(timeout=5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop()
