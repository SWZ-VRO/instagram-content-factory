"""
Background watcher for content/masters/ (§10). Deliberately polls the
filesystem rather than using OS file-change events (watchdog/inotify):
bind-mounted Docker volumes on Windows/Mac frequently fail to propagate
inotify events reliably, and polling is simple, portable, and plenty fast
enough at this scale (a handful of master drops at a time, not
thousands/second).

Runs as a daemon thread started from the FastAPI app's lifespan (see
backend/main.py's `start()`/`stop()` calls) -- a proper Celery-based worker
replaces this in Phase 6 without changing the underlying pipeline
(backend/services/master_import.py is already fully decoupled from how or
when it gets invoked, so swapping the caller is a small change).
"""
import logging
import threading
import time

from backend.core.config import settings
from backend.core.database import SessionLocal
from backend.services.master_import import scan_and_import

logger = logging.getLogger("icf.watcher")

_stop_event = threading.Event()
_thread: threading.Thread | None = None


def _run_loop() -> None:
    logger.info(
        "watcher started, polling %s every %.1fs", settings.MASTERS_DIR, settings.WATCHER_POLL_INTERVAL_SECONDS
    )
    while not _stop_event.is_set():
        try:
            db = SessionLocal()
            try:
                summary = scan_and_import(db)
                if summary.processed:
                    logger.info(
                        "watcher cycle: %d file(s) seen, %d ready",
                        len(summary.processed),
                        summary.ready_count,
                    )
            finally:
                db.close()
        except Exception:  # noqa: BLE001 -- the loop must survive any single bad cycle (§52)
            logger.exception("watcher cycle failed, will retry next poll")
        _stop_event.wait(settings.WATCHER_POLL_INTERVAL_SECONDS)


def start() -> None:
    global _thread
    if not settings.WATCHER_ENABLED:
        logger.info("watcher disabled (WATCHER_ENABLED=false)")
        return
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_run_loop, name="icf-watcher", daemon=True)
    _thread.start()


def stop() -> None:
    _stop_event.set()
    if _thread is not None:
        _thread.join(timeout=5)


if __name__ == "__main__":
    # Standalone run: `python -m backend.workers.watcher` -- useful for
    # local debugging without spinning up the whole API.
    logging.basicConfig(level=logging.INFO)
    start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop()
