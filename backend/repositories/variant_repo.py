from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.enums import VariantStatus
from backend.models.variant import Variant


def get(db: Session, variant_id: str) -> Variant | None:
    return db.get(Variant, variant_id)


def get_by_code(db: Session, variant_code: str) -> Variant | None:
    return db.execute(select(Variant).where(Variant.variant_code == variant_code)).scalar_one_or_none()


def get_by_sha256(db: Session, sha256: str) -> Variant | None:
    return db.execute(select(Variant).where(Variant.sha256 == sha256)).scalar_one_or_none()


def create(
    db: Session,
    *,
    master_id: str,
    variant_code: str,
    filename: str,
    filepath: str,
    sha256: str,
    transform: str | None = None,
    duration_seconds: float | None = None,
) -> Variant:
    variant = Variant(
        master_id=master_id,
        variant_code=variant_code,
        filename=filename,
        filepath=filepath,
        sha256=sha256,
        transform=transform,
        duration_seconds=duration_seconds,
        status=VariantStatus.MISSING_CAPTION,  # no caption yet at creation time -- §13
    )
    db.add(variant)
    db.commit()
    db.refresh(variant)
    return variant


def list_variants(
    db: Session,
    *,
    status: VariantStatus | None = None,
    master_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Variant]:
    stmt = select(Variant)
    if status is not None:
        stmt = stmt.where(Variant.status == status)
    if master_id is not None:
        stmt = stmt.where(Variant.master_id == master_id)
    stmt = stmt.order_by(Variant.created_at.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def counts_by_status(db: Session) -> dict[str, int]:
    stmt = select(Variant.status, func.count()).group_by(Variant.status)
    rows = db.execute(stmt).all()
    counts = {status.value: 0 for status in VariantStatus}
    for status, n in rows:
        counts[status.value] = n
    return counts
