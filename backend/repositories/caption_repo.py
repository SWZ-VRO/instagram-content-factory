from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.caption import Caption
from backend.models.enums import VariantStatus
from backend.models.variant import Variant


def get_for_variant(db: Session, variant_id: str) -> Caption | None:
    return db.execute(select(Caption).where(Caption.variant_id == variant_id)).scalar_one_or_none()


def attach(db: Session, *, variant_id: str, text: str, source: str = "csv") -> Caption:
    """
    Attach a caption to a variant verbatim (§11 -- never reformulated) and
    flip the variant out of MISSING_CAPTION into AVAILABLE if it was waiting
    only on this. Idempotent: re-attaching updates the text in place rather
    than erroring, since captions can be corrected before a variant is ever
    scheduled.
    """
    existing = get_for_variant(db, variant_id)
    if existing is not None:
        existing.text = text
        existing.source = source
        caption = existing
    else:
        caption = Caption(variant_id=variant_id, text=text, source=source)
        db.add(caption)

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
