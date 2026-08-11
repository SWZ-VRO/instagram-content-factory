"""Small test-only helpers to stand up an account/master/variant(+caption)
without repeating boilerplate in every test."""
import uuid

from sqlalchemy.orm import Session

from backend.models.account import Account
from backend.models.enums import AccountStatus, VariantStatus
from backend.models.caption import Caption
from backend.models.master import Master
from backend.models.variant import Variant


def make_account(db: Session, *, username: str | None = None, active: bool = True) -> Account:
    account = Account(
        username=username or f"ig_{uuid.uuid4().hex[:8]}",
        status=AccountStatus.ACTIVE if active else AccountStatus.PAUSED,
        active=active,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def make_master(db: Session, *, master_code: str | None = None) -> Master:
    code = master_code or f"MASTER_{uuid.uuid4().hex[:6].upper()}"
    master = Master(master_code=code, filename=f"{code}.mp4", filepath=f"/content/masters/{code}.mp4", sha256=uuid.uuid4().hex)
    db.add(master)
    db.commit()
    db.refresh(master)
    return master


def make_variant(
    db: Session, master: Master, *, index: int = 1, with_caption: bool = True, status: VariantStatus | None = None
) -> Variant:
    code = f"{master.master_code}_V{index:02d}"
    variant = Variant(
        master_id=master.id,
        variant_code=code,
        filename=f"{code}.mp4",
        filepath=f"/content/variants/{code}.mp4",
        sha256=uuid.uuid4().hex,
        status=status or (VariantStatus.MISSING_CAPTION if not with_caption else VariantStatus.AVAILABLE),
    )
    db.add(variant)
    db.commit()
    db.refresh(variant)

    if with_caption:
        caption = Caption(variant_id=variant.id, text=f"Caption for {code}", source="csv")
        db.add(caption)
        variant.status = VariantStatus.AVAILABLE
        db.commit()
        db.refresh(variant)

    return variant
