"""
Import every model here so `Base.metadata` is fully populated for
Alembic autogenerate and for `Base.metadata.create_all()` in tests.
"""
from backend.models.account import Account, AccountConnection  # noqa: F401
from backend.models.calendar_plan import CalendarPlan  # noqa: F401
from backend.models.caption import Caption  # noqa: F401
from backend.models.log import LogEntry  # noqa: F401
from backend.models.master import Master  # noqa: F401
from backend.models.publishing import PublishingEvent, PublishingJob  # noqa: F401
from backend.models.scheduled_post import ScheduledPost  # noqa: F401
from backend.models.setting import Setting  # noqa: F401
from backend.models.variant import Variant  # noqa: F401

__all__ = [
    "Account",
    "AccountConnection",
    "CalendarPlan",
    "Caption",
    "LogEntry",
    "Master",
    "PublishingEvent",
    "PublishingJob",
    "ScheduledPost",
    "Setting",
    "Variant",
]
