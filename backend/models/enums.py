"""
All status enums live here in one place, mirroring the vocabulary used
throughout the spec (§4, §18, §35 etc.) so the DB, API and dashboard never
disagree on what a status string means.
"""
import enum


class VariantStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    MISSING_CAPTION = "MISSING_CAPTION"
    RESERVED = "RESERVED"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"

    @classmethod
    def consumed_statuses(cls) -> tuple["VariantStatus", ...]:
        """Statuses that make a variant unavailable for (re)allocation -- §4/§15."""
        return (cls.RESERVED, cls.SCHEDULED, cls.PUBLISHED)


class MasterStatus(str, enum.Enum):
    IMPORTED = "IMPORTED"
    PROCESSING = "PROCESSING"
    READY = "READY"
    FAILED = "FAILED"


class AccountStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"


class ConnectionStatus(str, enum.Enum):
    CONNECTED = "CONNECTED"
    TOKEN_EXPIRING = "TOKEN_EXPIRING"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"


class ScheduledPostStatus(str, enum.Enum):
    """Mirrors VariantStatus's consumed states 1:1 (RESERVED/SCHEDULED/
    PUBLISHED) so the partial unique index condition on scheduled_posts.status
    and VariantStatus.consumed_statuses() never drift apart. RESERVED = part
    of a DRAFT/REVIEW calendar plan not yet approved; SCHEDULED = plan was
    approved (§37) and the Publishing Worker may act on it; CANCELLED = the
    slot was released without ever publishing (e.g. plan rejected)."""
    RESERVED = "RESERVED"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PublishingJobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    UPLOADING = "UPLOADING"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class CalendarPlanStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    REVIEW = "REVIEW"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ErrorCode(str, enum.Enum):
    """Centralized in the Errors page -- §35."""
    MISSING_CAPTION = "MISSING_CAPTION"
    INVALID_MEDIA = "INVALID_MEDIA"
    UPLOAD_FAILED = "UPLOAD_FAILED"
    PUBLISH_FAILED = "PUBLISH_FAILED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    RATE_LIMIT = "RATE_LIMIT"
    ACCOUNT_AUTH_ERROR = "ACCOUNT_AUTH_ERROR"
    SCHEDULING_CONFLICT = "SCHEDULING_CONFLICT"
    CONTENT_SHORTAGE = "CONTENT_SHORTAGE"
