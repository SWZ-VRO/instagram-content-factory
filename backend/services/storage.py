"""
Pluggable permanent storage for master/variant video files -- see
STORAGE_BACKEND in backend/core/config.py for when/why "supabase" is
needed instead of "local".

Every video-pipeline module (ffmpeg_runner, qc, hashing) still reads/writes
real files on local disk while actually doing work -- ffmpeg/ffprobe need
that. This module only handles the "upload to permanent storage" step
master_import.py runs once ffmpeg is done with a file, so the result
survives a host with no persistent disk.
"""
from pathlib import Path

import httpx

from backend.core.config import settings


class StorageError(Exception):
    pass


class LocalStorage:
    """No-op passthrough: the file already lives permanently at its given
    local path (content/variants/, content/archive/, ...) -- this is what
    Docker Compose / Phases 1-5 were built and tested against."""

    def upload(self, local_path: Path, remote_key: str) -> str:  # noqa: ARG002 -- remote_key unused by design
        return str(local_path)


class SupabaseStorage:
    """Uploads to a Supabase Storage bucket via its plain REST API (no
    supabase-py SDK dependency -- same pattern as
    backend/publishers/instagram_official.py talking to Meta directly with
    httpx, so there's one HTTP-client idiom in the whole codebase)."""

    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
            raise StorageError(
                "SUPABASE_URL/SUPABASE_SERVICE_KEY are not configured -- "
                "set STORAGE_BACKEND=local or provide both."
            )
        self._base = settings.SUPABASE_URL.rstrip("/")
        self._bucket = settings.SUPABASE_STORAGE_BUCKET
        # Authorization: Bearer alone is enough to authenticate against the
        # Storage REST API with either key format. Deliberately NOT also
        # sending an `apikey` header: Supabase's newer secret-key format
        # (sb_secret_... -- the one replacing the legacy service_role key)
        # has a browser-detection guard that rejects requests carrying the
        # secret in `apikey`, since that header is the client-side/anon-key
        # convention. Bearer-only works for both the legacy JWT service_role
        # key and the new sb_secret_ format.
        self._headers = {"Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}"}
        self._client = http_client or httpx.Client(timeout=120.0)

    def upload(self, local_path: Path, remote_key: str) -> str:
        """Uploads the file and returns its permanent public URL. The
        bucket must be configured as public in the Supabase dashboard --
        Instagram needs to fetch this URL directly (see
        backend/publishers/instagram_official.py module docstring)."""
        url = f"{self._base}/storage/v1/object/{self._bucket}/{remote_key}"
        with open(local_path, "rb") as f:
            resp = self._client.post(
                url,
                content=f.read(),
                headers={**self._headers, "Content-Type": "video/mp4", "x-upsert": "true"},
            )
        if resp.status_code >= 400:
            raise StorageError(f"Supabase upload failed for {remote_key}: {resp.status_code} {resp.text[:300]}")
        return f"{self._base}/storage/v1/object/public/{self._bucket}/{remote_key}"


def get_storage():
    if settings.STORAGE_BACKEND == "supabase":
        return SupabaseStorage()
    return LocalStorage()
