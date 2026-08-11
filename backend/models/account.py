from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.models.enums import AccountStatus, ConnectionStatus
from backend.models.mixins import TimestampMixin, UUIDPKMixin


class Account(UUIDPKMixin, TimestampMixin, Base):
    """
    An Instagram account the factory can publish to. Architected to scale to
    500-1000 rows without changes (§16) -- it's a plain indexed table, no
    per-account sharding needed at this size.
    """
    __tablename__ = "accounts"

    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)

    # Instagram Business Account id + linked Facebook Page id, populated once
    # the account is connected via OAuth (Phase 5). Nullable until then.
    ig_business_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    page_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")

    status: Mapped[AccountStatus] = mapped_column(
        SAEnum(AccountStatus, name="account_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AccountStatus.ACTIVE,
    )
    connection_status: Mapped[ConnectionStatus] = mapped_column(
        SAEnum(ConnectionStatus, name="connection_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ConnectionStatus.DISCONNECTED,
    )
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    daily_min_posts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    daily_max_posts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    connections: Mapped[list["AccountConnection"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    scheduled_posts: Mapped[list["ScheduledPost"]] = relationship(back_populates="account")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Account {self.username} status={self.status} conn={self.connection_status}>"


class AccountConnection(UUIDPKMixin, TimestampMixin, Base):
    """
    OAuth credential history for an account. Kept separate from Account so we
    can rotate/refresh tokens (and keep an audit trail) without mutating the
    account row itself. The token is ALWAYS encrypted at rest (§53) -- see
    backend/core/security.py. Never expose access_token_encrypted via the API.
    """
    __tablename__ = "account_connections"

    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True)

    access_token_encrypted: Mapped[str] = mapped_column(String, nullable=False)
    token_type: Mapped[str] = mapped_column(String(32), nullable=False, default="long_lived")
    refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped["Account"] = relationship(back_populates="connections")
