"""
Thin orchestration layer between the API routes and the repositories.
Phase 1 is CRUD-only; account CONNECT (OAuth) lands in Phase 5 and will add
`connect()`/`refresh_connection()` here, backed by an InstagramOfficialPublisher.
"""
from sqlalchemy.orm import Session

from backend.models.account import Account
from backend.repositories import account_repo


class AccountAlreadyExists(Exception):
    pass


def create_account(
    db: Session, *, username: str, timezone: str = "UTC", daily_min_posts: int = 1, daily_max_posts: int = 5
) -> Account:
    if account_repo.get_by_username(db, username) is not None:
        raise AccountAlreadyExists(username)
    return account_repo.create(
        db, username=username, timezone=timezone, daily_min_posts=daily_min_posts, daily_max_posts=daily_max_posts
    )


def list_accounts(db: Session, *, limit: int = 100, offset: int = 0) -> list[Account]:
    return account_repo.list_accounts(db, limit=limit, offset=offset)


def get_account(db: Session, account_id: str) -> Account | None:
    return account_repo.get(db, account_id)
