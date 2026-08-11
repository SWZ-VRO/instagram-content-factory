"""
Serves generated variant files over plain HTTP(S) -- required because
Instagram's Content Publishing API fetches video from a public URL rather
than accepting a direct upload (see backend/publishers/instagram_official.py
module docstring). Deliberately scoped to VARIANTS_DIR only (never masters/
captions/archive) and to filenames that already exist as a known variant in
the DB, so this can never become an arbitrary file server.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.api.deps import get_db
from backend.core.config import settings
from backend.repositories import variant_repo
from backend.services.media_service import public_media_url  # noqa: F401 -- re-exported for callers importing from here

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/variants/{variant_code}.mp4")
def get_variant_file(variant_code: str, db: Session = Depends(get_db)):
    variant = variant_repo.get_by_code(db, variant_code)
    if variant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="variant not found")

    path = settings.VARIANTS_DIR / variant.filename
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="variant file missing on disk")

    return FileResponse(path, media_type="video/mp4", filename=variant.filename)
