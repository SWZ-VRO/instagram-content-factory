from datetime import datetime

from sqlalchemy import JSON, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.core.database import Base
from backend.models.enums import CalendarPlanStatus
from backend.models.mixins import TimestampMixin, UUIDPKMixin


class CalendarPlan(UUIDPKMixin, TimestampMixin, Base):
    """
    One 30-day generation run (§21, §37). Posts stay DRAFT/REVIEW until the
    user clicks APPROVE PLAN -- only then do scheduled_posts move from
    tentative to reserved-for-real and the Publishing Worker is allowed to
    act on them (§37, §13 workflow).
    """
    __tablename__ = "calendar_plans"

    status: Mapped[CalendarPlanStatus] = mapped_column(
        SAEnum(CalendarPlanStatus, name="calendar_plan_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=CalendarPlanStatus.DRAFT,
        index=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    params: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # generation params snapshot (day windows, etc.)

    scheduled_posts: Mapped[list["ScheduledPost"]] = relationship(back_populates="calendar_plan")  # noqa: F821
