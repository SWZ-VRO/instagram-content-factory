from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.account import Account


def create(db: Session, *, username: str, timezone: str = "UTC", daily_min_posts: int = 1, daily_max_posts: int = 5) -> Account:
    account = Account(
        username=username,
        timezone=timezone,
        daily_min_posts=daily_min_posts,
        daily_max_posts=daily_max_posts,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def get(db: Session, account_id: str) -> Account | None:
    return db.get(Account, account_id)


def get_by_username(db: Session, username: str) -> Account | None:
    return db.execute(select(Account).where(Account.username == username)).scalar_one_or_none()


def get_by_ig_business_id(db: Session, ig_business_id: str) -> Account | None:
    return db.execute(select(Account).where(Account.ig_business_id == ig_business_id)).scalar_one_or_none()


def list_accounts(db: Session, *, limit: int = 100, offset: int = 0) -> list[Account]:
    stmt = select(Account).order_by(Account.created_at.desc()).limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def count(db: Session) -> int:
    return db.execute(select(func.count()).select_from(Account)).scalar_one()


def count_active(db: Session) -> int:
    return db.execute(select(func.count()).select_from(Account).where(Account.active.is_(True))).scalar_one()
