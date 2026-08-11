"""
Public media URL construction -- shared by the media-serving route
(backend/api/routes/media.py) and the publishing pipeline
(backend/services/publishing_pipeline.py). Lives here, not in the route
module, so services never has to import from api/ (§41 layering: api
depends on services, never the reverse).
"""
from backend.core.config import settings
from backend.models.variant import Variant


def public_media_url(variant: Variant) -> str:
    """
    The URL to hand Instagram for this variant.

      - STORAGE_BACKEND=supabase: the variant's own permanent storage URL
        (set at import time -- backend/services/master_import.py) is
        already public; used directly.
      - STORAGE_BACKEND=local: built from PUBLIC_BASE_URL, pointing back
        at our own /media/variants route (backend/api/routes/media.py).
        Raises if PUBLIC_BASE_URL isn't configured, rather than silently
        building a URL Instagram's servers could never reach.
    """
    if variant.storage_url:
        return variant.storage_url
    if not settings.PUBLIC_BASE_URL:
        raise RuntimeError("PUBLIC_BASE_URL is not configured -- see README 'Instagram connection'")
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}/media/variants/{variant.variant_code}.mp4"
