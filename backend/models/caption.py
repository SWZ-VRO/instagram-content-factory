from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.models.mixins import TimestampMixin, UUIDPKMixin


class Caption(UUIDPKMixin, TimestampMixin, Base):
    """
    Exactly the text the user supplied -- never touched, reformulated,
    translated or decorated by the app (§11). One caption per variant,
    enforced by the unique FK below.
    """
    __tablename__ = "captions"

    variant_id: Mapped[str] = mapped_column(
        ForeignKey("variants.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="csv")  # "csv" | "txt"

    variant: Mapped["Variant"] = relationship(back_populates="caption")  # noqa: F821
