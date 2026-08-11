from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base
from backend.models.mixins import TimestampMixin, UUIDPKMixin


class Setting(UUIDPKMixin, TimestampMixin, Base):
    """Key/value runtime settings editable from the dashboard (e.g. posting
    time slots, global pause flag) without redeploying."""
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
