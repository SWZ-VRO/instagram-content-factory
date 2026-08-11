"""Pydantic request/response models. Kept separate from SQLAlchemy models so
the DB schema can evolve without automatically changing the public API."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import AccountStatus, ConnectionStatus, MasterStatus, VariantStatus


class AccountCreate(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    timezone: str = "UTC"
    daily_min_posts: int = Field(default=1, ge=0)
    daily_max_posts: int = Field(default=5, ge=0)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    timezone: str
    status: AccountStatus
    connection_status: ConnectionStatus
    daily_min_posts: int
    daily_max_posts: int
    active: bool
    created_at: datetime


class ManualConnectRequest(BaseModel):
    ig_business_id: str = Field(min_length=1)
    access_token: str = Field(min_length=1)


class OAuthAuthorizeResponse(BaseModel):
    authorize_url: str
    state: str


class MasterSummaryOut(BaseModel):
    id: uuid.UUID
    master_code: str
    filename: str
    status: MasterStatus
    created_at: datetime
    variant_count: int
    available_count: int
    consumed_count: int
    accounts_used: int


class VariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    master_id: uuid.UUID
    variant_code: str
    filename: str
    status: VariantStatus
    created_at: datetime


class CaptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    variant_id: uuid.UUID
    text: str
    source: str


class CaptionImportResult(BaseModel):
    attached: int
    errors: list[str] = []


class MasterImportOutcomeOut(BaseModel):
    master_code: str
    status: str
    variants_created: int
    reasons: list[str] = []


class ImportSummaryOut(BaseModel):
    processed: list[MasterImportOutcomeOut]
    ready_count: int


class InventoryRowOut(BaseModel):
    master_code: str
    variant_code: str
    caption_text: str | None
    account_username: str | None
    scheduled_at_utc: datetime | None
    status: str


class CalendarGenerateRequest(BaseModel):
    start_date: date | None = None  # defaults to tomorrow (UTC) if omitted
    days: int | None = Field(default=None, ge=1, le=365)


class CalendarGenerateResponse(BaseModel):
    plan_id: uuid.UUID
    required_posts: int
    available_variants_at_start: int
    reserved_count: int
    shortage: int
    content_shortage: bool


class CalendarPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    approved_at: datetime | None
    params: dict | None
    created_at: datetime


class LogEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    timestamp: datetime
    level: str
    code: str | None
    message: str


class PublishingJobOut(BaseModel):
    id: uuid.UUID
    scheduled_post_id: uuid.UUID
    status: str
    attempts: int
    last_error: str | None
    account_username: str | None
    variant_code: str | None
    scheduled_at_utc: datetime | None


class PublishingStatusOut(BaseModel):
    paused: bool
    due_now: int
    by_status: dict[str, int]


class DashboardSummary(BaseModel):
    accounts_total: int
    accounts_active: int
    masters_total: int
    variants_by_status: dict[str, int]
    missing_captions: int
    dry_run: bool
