from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.security import decrypt_token, encrypt_token
from backend.models.account import AccountConnection


def store_token(
    db: Session, *, account_id, access_token_plain: str, expires_at: datetime | None, token_type: str = "long_lived"
) -> AccountConnection:
    """Tokens are encrypted before they ever touch the DB (§53) -- see
    backend/core/security.py. Callers must never log `access_token_plain`."""
    connection = AccountConnection(
        account_id=account_id,
        access_token_encrypted=encrypt_token(access_token_plain),
        token_type=token_type,
        refreshed_at=datetime.now(expires_at.tzinfo) if expires_at else None,
        expires_at=expires_at,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


def get_latest(db: Session, account_id) -> AccountConnection | None:
    stmt = (
        select(AccountConnection)
        .where(AccountConnection.account_id == account_id)
        .order_by(AccountConnection.created_at.desc())
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_decrypted_token(db: Session, account_id) -> str | None:
    connection = get_latest(db, account_id)
    if connection is None:
        return None
    return decrypt_token(connection.access_token_encrypted)
