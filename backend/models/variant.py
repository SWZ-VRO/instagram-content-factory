from sqlalchemy import ForeignKey, Index, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.models.enums import VariantStatus
from backend.models.mixins import TimestampMixin, UUIDPKMixin


class Variant(UUIDPKMixin, TimestampMixin, Base):
    """
    A single publishable rendition of a master (e.g. MASTER_001_V01).

    THE CORE INVARIANT OF THE WHOLE SYSTEM (§2, §15, §56 rule 1-2) lives on
    this table: a variant may be consumed (RESERVED/SCHEDULED/PUBLISHED) by
    at most one scheduled_posts row, ever. That is enforced two ways:

      1. `status` itself -- the scheduler only ever picks AVAILABLE variants.
      2. A DB-level partial unique index on scheduled_posts(variant_id) for
         rows whose status is RESERVED/SCHEDULED/PUBLISHED (see
         ScheduledPost below). That index is the actual guarantee -- #1 is
         just the fast path that avoids contention in the common case.
    """
    __tablename__ = "variants"
    __table_args__ = (
        Index("ix_variants_master_status", "master_id", "status"),
    )

    master_id: Mapped[str] = mapped_column(ForeignKey("masters.id", ondelete="CASCADE"), nullable=False, index=True)

    variant_code: Mapped[str] = mapped_column(String(96), unique=True, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    filepath: Mapped[str] = mapped_column(String(1024), nullable=False)

    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    perceptual_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)

    # Set only when STORAGE_BACKEND=supabase (backend/services/storage.py):
    # the permanent public URL of this variant's file. When set, this is
    # what gets handed to Instagram (backend/services/media_service.py) --
    # `filepath`/`filename` above then only describe where the file was
    # produced locally during processing, not where it lives long-term.
    storage_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)
    transform: Mapped[str | None] = mapped_column(String(64), nullable=True)  # crop/zoom/reframe/... (§8)

    status: Mapped[VariantStatus] = mapped_column(
        SAEnum(VariantStatus, name="variant_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=VariantStatus.AVAILABLE,
        index=True,
    )

    master: Mapped["Master"] = relationship(back_populates="variants")  # noqa: F821
    caption: Mapped["Caption | None"] = relationship(  # noqa: F821
        back_populates="variant", uselist=False, cascade="all, delete-orphan"
    )
    scheduled_posts: Mapped[list["ScheduledPost"]] = relationship(back_populates="variant")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Variant {self.variant_code} status={self.status}>"
