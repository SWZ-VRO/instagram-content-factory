from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.caption import Caption
from backend.models.enums import VariantStatus
from backend.models.variant import Variant


def get_for_variant(db: Session, variant_id: str) -> Caption | None:
    return db.execute(select(Caption).where(Caption.variant_id == variant_id)).scalar_one_or_none()


def attach(db: Session, *, variant_id: str, text: str, source: str = "csv", flip_status: bool = True) -> Caption:
    """
    Attach a caption to a variant verbatim (§11 -- never reformulated).
    Idempotent: re-attaching updates the text in place rather than
    erroring, since captions can be corrected before a variant is ever
    scheduled.

    `flip_status` (default True): flip MISSING_CAPTION -> AVAILABLE
    immediately. Pass `flip_status=False` when a caller has a further
    required step before the variant is really publishable (as of this
    writing: backend/services/caption_pipeline.py burns the caption onto
    the video before the variant may become AVAILABLE -- flipping it here
    first would make the variant schedulable during that window, before
    the burn has even been attempted).
    """
    existing = get_for_variant(db, variant_id)
    if existing is not None:
        existing.text = text
        existing.source = source
        caption = existing
    else:
        caption = Caption(variant_id=variant_id, text=text, source=source)
        db.add(caption)

    if flip_status:
        variant = db.get(Variant, variant_id)
        if variant is not None and variant.status == VariantStatus.MISSING_CAPTION:
            variant.status = VariantStatus.AVAILABLE

    db.commit()
    db.refresh(caption)
    return caption


def list_missing_captions(db: Session, *, limit: int = 100, offset: int = 0) -> list[Variant]:
    stmt = (
        select(Variant)
        .where(Variant.status == VariantStatus.MISSING_CAPTION)
        .order_by(Variant.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(stmt).scalars().all())
