from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.core.database import Base
from backend.models.mixins import UUIDPKMixin


class LogEntry(UUIDPKMixin, Base):
    """Structured application log, queryable from the dashboard's Errors page
    (§35) without grepping container logs."""
    __tablename__ = "logs"

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="INFO")
    code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # ErrorCode value, if applicable
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
