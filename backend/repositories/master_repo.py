from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.enums import MasterStatus
from backend.models.master import Master
from backend.models.variant import Variant


def get_by_sha256(db: Session, sha256: str) -> Master | None:
    return db.execute(select(Master).where(Master.sha256 == sha256)).scalar_one_or_none()


def get_by_code(db: Session, master_code: str) -> Master | None:
    return db.execute(select(Master).where(Master.master_code == master_code)).scalar_one_or_none()


def get_with_phash(db: Session) -> list[Master]:
    """Masters that have a perceptual hash computed -- used by near-duplicate
    detection (§14) in backend/services/master_import.py."""
    return list(db.execute(select(Master).where(Master.perceptual_hash.is_not(None))).scalars().all())


def create(
    db: Session,
    *,
    master_code: str,
    filename: str,
    filepath: str,
    sha256: str,
    perceptual_hash: str | None = None,
    duration_seconds: float | None = None,
    status: MasterStatus = MasterStatus.IMPORTED,
) -> Master:
    master = Master(
        master_code=master_code,
        filename=filename,
        filepath=filepath,
        sha256=sha256,
        perceptual_hash=perceptual_hash,
        duration_seconds=duration_seconds,
        status=status,
    )
    db.add(master)
    db.commit()
    db.refresh(master)
    return master


def list_masters(db: Session, *, limit: int = 100, offset: int = 0) -> list[Master]:
    stmt = select(Master).order_by(Master.created_at.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def count(db: Session) -> int:
    return db.execute(select(func.count()).select_from(Master)).scalar_one()


def next_master_code(db: Session) -> str:
    """MASTER_001, MASTER_002, ... -- used by the (Phase 2) watcher when the
    dropped filename doesn't already look like a master code."""
    existing = db.execute(select(func.count()).select_from(Master)).scalar_one()
    return f"MASTER_{existing + 1:03d}"


def variant_count(db: Session, master_id: str) -> int:
    return db.execute(select(func.count()).select_from(Variant).where(Variant.master_id == master_id)).scalar_one()
