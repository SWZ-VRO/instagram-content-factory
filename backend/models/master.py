from sqlalchemy import String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.models.enums import MasterStatus
from backend.models.mixins import TimestampMixin, UUIDPKMixin


class Master(UUIDPKMixin, TimestampMixin, Base):
    """
    A master video dropped into /content/masters by the user (from ComfyUI).
    master_code is the human-readable id (e.g. "MASTER_001") that variants
    reference in their own codes -- §7.
    """
    __tablename__ = "masters"

    master_code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    filepath: Mapped[str] = mapped_column(String(1024), nullable=False)

    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    perceptual_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)

    status: Mapped[MasterStatus] = mapped_column(
        SAEnum(MasterStatus, name="master_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=MasterStatus.IMPORTED,
    )

    variants: Mapped[list["Variant"]] = relationship(back_populates="master", cascade="all, delete-orphan")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Master {self.master_code} status={self.status}>"
