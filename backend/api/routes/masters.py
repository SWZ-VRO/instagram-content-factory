from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.api.deps import get_db
from backend.api.schemas import ImportSummaryOut, MasterImportOutcomeOut, MasterSummaryOut
from backend.core.config import settings
from backend.services import master_service
from backend.services.master_import import import_one_master, scan_and_import
from backend.validators.content import is_supported_video_file

router = APIRouter(prefix="/masters", tags=["masters"])


@router.get("", response_model=list[MasterSummaryOut])
def list_masters(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    """§30 Masters page: includes variant/available/consumed/accounts-used counts."""
    summaries = master_service.list_masters_with_counts(db, limit=limit, offset=offset)
    return [
        MasterSummaryOut(
            id=s.master.id,
            master_code=s.master.master_code,
            filename=s.master.filename,
            status=s.master.status,
            created_at=s.master.created_at,
            variant_count=s.variant_count,
            available_count=s.available_count,
            consumed_count=s.consumed_count,
            accounts_used=s.accounts_used,
        )
        for s in summaries
    ]


@router.post("/import", response_model=ImportSummaryOut)
def import_masters(db: Session = Depends(get_db)):
    """
    "IMPORT NOW" (§10): force-processes every file currently sitting in
    content/masters/ synchronously, without waiting for the background
    watcher's next poll. Same pipeline either way -- see
    backend/services/master_import.py.
    """
    summary = scan_and_import(db)
    return ImportSummaryOut(
        processed=[
            MasterImportOutcomeOut(
                master_code=o.master_code, status=o.status, variants_created=o.variants_created, reasons=o.reasons
            )
            for o in summary.processed
        ],
        ready_count=summary.ready_count,
    )


@router.post("/upload", response_model=MasterImportOutcomeOut)
async def upload_master(file: UploadFile, db: Session = Depends(get_db)):
    """
    Push-based alternative to the folder watcher (§10), for deployments
    with no local filesystem to drop files into (e.g. a cloud host with no
    persistent disk -- see backend/services/storage.py). Runs the exact
    same import pipeline as the watcher/IMPORT NOW, just fed by an
    uploaded file instead of a folder scan; no stability-check needed here
    since an HTTP upload is only "received" once fully read.

    `import_one_master` is a heavy, fully synchronous call (ffmpeg
    subprocesses, and in "supabase" storage mode a blocking HTTP upload) --
    run via `run_in_threadpool` rather than awaited directly, so it doesn't
    block this process's single asyncio event loop (and every other
    in-flight request) for the whole duration of one video's processing.
    """
    filename = file.filename or "upload.mp4"
    settings.MASTERS_DIR.mkdir(parents=True, exist_ok=True)
    destination = settings.MASTERS_DIR / filename
    if not is_supported_video_file(destination):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"unsupported file type: {destination.suffix}")

    with open(destination, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)

    outcome = await run_in_threadpool(import_one_master, db, destination)
    return MasterImportOutcomeOut(
        master_code=outcome.master_code, status=outcome.status, variants_created=outcome.variants_created, reasons=outcome.reasons
    )
