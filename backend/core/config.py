"""
Central application configuration.

Everything that used to be a hard-coded constant in the spec (MIN_VARIANTS,
MIN_MASTER_GAP_DAYS, DRY_RUN, ...) lives here, sourced from environment
variables (see .env.example at the repo root). Nothing else in the codebase
should read os.environ directly -- import `settings` from this module instead.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "Instagram Content Factory"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # --- Database ---
    DATABASE_URL: str = "postgresql+psycopg://icf:icf@localhost:5432/icf"

    # --- Redis / queue (used from Phase 2+, wired here so config is stable) ---
    REDIS_URL: str = "redis://localhost:6379/0"

    # --- Secrets ---
    # Used to encrypt account access tokens at rest (Fernet). Generate with:
    #   python -c "import secrets; print(secrets.token_urlsafe(32))"
    SECRET_KEY: str = "change-me-in-.env-this-is-not-a-real-secret"

    # --- Content pipeline paths ---
    # Default assumes the process is started from the repo root
    # (instagram-content-factory/), which is what README/docker-compose do.
    # In Docker this is overridden to /app/content via env (see
    # docker-compose.yml) so it's unambiguous regardless of WORKDIR.
    CONTENT_ROOT: Path = Path("content")

    @property
    def MASTERS_DIR(self) -> Path:
        return self.CONTENT_ROOT / "masters"

    @property
    def PROCESSING_DIR(self) -> Path:
        return self.CONTENT_ROOT / "processing"

    @property
    def VARIANTS_DIR(self) -> Path:
        return self.CONTENT_ROOT / "variants"

    @property
    def CAPTIONS_DIR(self) -> Path:
        return self.CONTENT_ROOT / "captions"

    @property
    def READY_DIR(self) -> Path:
        return self.CONTENT_ROOT / "ready"

    @property
    def FAILED_DIR(self) -> Path:
        return self.CONTENT_ROOT / "failed"

    @property
    def ARCHIVE_DIR(self) -> Path:
        return self.CONTENT_ROOT / "archive"

    # --- Business rules (spec sections referenced in comments) ---
    MIN_VARIANTS: int = 5          # §8
    MAX_VARIANTS: int = 10         # §8
    MIN_MASTER_GAP_DAYS: int = 2   # §6
    REQUIRE_CAPTION: bool = True   # §13

    # --- 30-day calendar defaults (§21) ---
    DAY_1_3_POSTS: int = 2
    DAY_4_7_POSTS: int = 3
    DAY_8_30_MIN_POSTS: int = 3
    DAY_8_30_MAX_POSTS: int = 5
    CALENDAR_DAYS: int = 30

    # --- Publishing behavior ---
    DRY_RUN: bool = True           # §36 -- must be explicitly turned off to publish for real
    PUBLISHER: str = "instagram_official"  # or "third_party" once implemented (§19)

    # --- Rate limiting (soft ceilings -- see plan research notes, Meta's real
    # numbers vary by account and are impression-based, not fixed) ---
    IG_MAX_PUBLISHES_PER_ACCOUNT_PER_DAY: int = 25
    IG_MAX_API_CALLS_PER_ACCOUNT_PER_HOUR: int = 200

    # --- Video pipeline (§8-10) ---
    FFMPEG_BINARY: str = "ffmpeg"
    FFPROBE_BINARY: str = "ffprobe"
    FFMPEG_TIMEOUT_SECONDS: int = 600
    # Two consecutive "IMPORT NOW" size checks, this many seconds apart,
    # must agree before a file is considered fully written (§10 step 2:
    # "vérifier son intégrité" -- a file mid-copy must never be imported).
    FILE_STABILITY_CHECK_SECONDS: float = 1.0
    MIN_MASTER_DURATION_SECONDS: float = 1.0
    MAX_MASTER_DURATION_SECONDS: float = 900.0  # 15 min -- generous ceiling, catches obviously-wrong drops

    # Perceptual-hash Hamming distance below which two videos are considered
    # near-duplicates (§14). Compared only ACROSS masters/variants of
    # different masters -- variants of the *same* master are expected to
    # look similar by design and are never flagged against each other.
    PHASH_DUPLICATE_THRESHOLD: int = 6

    # Background watcher (Phase 2's stand-in for the Celery-based worker
    # that arrives in Phase 6 -- see backend/workers/watcher.py).
    WATCHER_ENABLED: bool = True
    WATCHER_POLL_INTERVAL_SECONDS: float = 5.0

    # --- Phase 5: Instagram OAuth + publishing ---
    # All blank by default -- the app is fully inert on this front until an
    # operator fills these in from their own Meta Developer App. See
    # README "Instagram connection" for the manual-token fallback, which
    # works without waiting on Meta App Review.
    IG_APP_ID: str = ""
    IG_APP_SECRET: str = ""
    IG_OAUTH_REDIRECT_URI: str = ""
    GRAPH_API_VERSION: str = "v21.0"  # bump only after checking Meta's changelog
    GRAPH_API_TIMEOUT_SECONDS: float = 30.0

    # Instagram's Content Publishing API fetches video from a public HTTPS
    # URL -- it does not accept a direct file upload. PUBLIC_BASE_URL must
    # be the backend's own publicly reachable origin (a real domain, or a
    # tunnel like ngrok in dev) serving /media/variants/<file> -- see
    # backend/api/routes/media.py. Left blank by default; the publisher
    # refuses to run rather than construct a URL Instagram can't reach.
    PUBLIC_BASE_URL: str = ""

    # Background Publishing Worker (§18, §51) -- polls for due SCHEDULED
    # posts. Same "thread now, Celery later" pattern as the watcher.
    PUBLISHING_WORKER_ENABLED: bool = True
    PUBLISHING_POLL_INTERVAL_SECONDS: float = 30.0
    MAX_PUBLISH_ATTEMPTS: int = 3
    RETRY_BACKOFF_BASE_SECONDS: float = 60.0  # doubles per attempt (§46)
    # Bounded container-processing poll per post, so one slow upload never
    # blocks the worker loop indefinitely (§18 UPLOADING -> SCHEDULED/PUBLISHED).
    CONTAINER_POLL_ATTEMPTS: int = 10
    CONTAINER_POLL_INTERVAL_SECONDS: float = 3.0

    # --- Storage backend for master/variant video files ---
    # "local": files live on local/container disk under CONTENT_ROOT --
    #   what Docker Compose (Phases 1-5) was built and tested against.
    # "supabase": files are uploaded to a Supabase Storage bucket and
    #   referenced by public URL -- required on any host with no
    #   persistent disk (e.g. Render's free tier, which wipes local files
    #   on every restart/redeploy). See backend/services/storage.py.
    # Local disk is still used TRANSIENTLY in "supabase" mode while ffmpeg
    # is actually running (it needs real files) -- this setting only
    # controls where things end up permanently.
    STORAGE_BACKEND: str = "local"
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""  # service_role key -- server-side only, never exposed to the frontend
    SUPABASE_STORAGE_BUCKET: str = "content"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
