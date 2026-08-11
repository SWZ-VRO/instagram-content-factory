"""
SocialPublisher abstraction (§19). Implementations are added phase by phase:

  - InstagramOfficialPublisher (below): direct Meta Graph API, container ->
    poll -> publish flow. Real HTTP calls land in Phase 5, once OAuth
    (Facebook Login for Business) exists to obtain account tokens -- there
    is nothing to authenticate with yet in Phase 1, so every method here is
    a documented NotImplementedError stub. This is intentional: §59
    forbids inventing endpoints or behavior that hasn't been verified
    against Meta's current docs, and none of that plumbing exists yet.
  - A ThirdPartyPublisher may be added later per §19, behind the same
    interface, if the operational cost of per-account Meta app review
    (see plan research notes) makes an authorized third-party provider a
    better fit for 100+ accounts. It will be implemented only after reading
    that provider's actual API docs -- never assumed.

Every concrete method must respect DRY_RUN (§36): when settings.DRY_RUN is
true, no network call may be made; callers pass dry_run through explicitly
so a publisher can never "forget" to check it.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class MediaContainer:
    container_id: str
    status: str  # IN_PROGRESS | FINISHED | ERROR (Graph API vocabulary)


@dataclass
class PublishResult:
    provider_post_id: str
    raw_response: dict[str, Any]


class SocialPublisher(ABC):
    """One implementation per provider. All methods raise the provider's own
    exception types on failure; callers (Publishing Worker, Phase 5) are
    responsible for classifying failures as retryable vs. definitive per §5."""

    @abstractmethod
    def connect_account(self, *, authorization_code: str) -> dict[str, Any]:
        """Exchange an OAuth authorization code for a long-lived token."""

    @abstractmethod
    def validate_account(self, *, ig_business_id: str, access_token: str) -> bool:
        """Confirm the account is a reachable Business/Creator account and
        the token is still valid."""

    @abstractmethod
    def refresh_connection(self, *, access_token: str) -> dict[str, Any]:
        """Exchange a long-lived token nearing expiry for a fresh one."""

    @abstractmethod
    def upload_media(self, *, ig_business_id: str, access_token: str, media_url: str, caption: str, dry_run: bool) -> MediaContainer:
        """Create a media container (Graph API: POST /{ig-user-id}/media)."""

    @abstractmethod
    def get_container_status(self, *, container_id: str, access_token: str) -> str:
        """Poll container status until FINISHED (Graph API has no webhook for this)."""

    @abstractmethod
    def publish_post(self, *, ig_business_id: str, access_token: str, container: MediaContainer, dry_run: bool) -> PublishResult:
        """Publish a FINISHED container (Graph API: POST /{ig-user-id}/media_publish)."""

    @abstractmethod
    def get_post_status(self, *, provider_post_id: str, access_token: str) -> dict[str, Any]:
        pass

    @abstractmethod
    def cancel_post(self, *, container_id: str, access_token: str) -> None:
        """Best-effort: once a container is FINISHED and published there is
        nothing to cancel on Instagram's side -- only pre-publish containers
        can be abandoned (simply never call publish_post on them)."""
