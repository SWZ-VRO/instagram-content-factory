"""
Direct Meta Graph API publisher.

Verified against Meta's current documentation while building this project
(Aug 2026) -- see the plan file and README "Instagram connection" for
citations. Two things are worth restating here because they shape every
method below:

  1. NO NATIVE SCHEDULING. The Content Publishing API has no
     publish_at/scheduled_publish_time parameter. "Scheduling" is entirely
     the Publishing Worker's job (backend/workers/publishing_worker.py):
     wake up at the right time, create a container, poll it, publish it.
  2. Video must be fetched by Instagram from a public HTTPS URL -- there is
     no direct-upload endpoint. `upload_media`'s `media_url` therefore has
     to be reachable from the public internet; see settings.PUBLIC_BASE_URL
     and backend/api/routes/media.py.

The OAuth piece (connect_account / refresh_connection) follows the
"Facebook Login for Business" pattern (Page access token -> linked
`instagram_business_account` -> IG user id), which is the flow recommended
for managing many accounts under one Business Manager (see plan research
notes). Meta has since also introduced a separate "Instagram API with
Instagram Login" flow with different endpoints (graph.instagram.com) not
implemented here. Before relying on this in production: re-check the exact
scope names and endpoint shapes against developers.facebook.com, since
permission names have changed before (e.g. instagram_content_publish ->
instagram_business_content_publish) and could again.
"""
from typing import Any

import httpx

from backend.core.config import settings
from backend.publishers.base import MediaContainer, PublishResult, SocialPublisher
from backend.publishers.exceptions import (
    PublisherAuthError,
    PublisherError,
    PublisherPermanentError,
    PublisherRateLimitError,
    PublisherTemporaryError,
)

# Meta error subcodes that mean "your token is dead", vs. "you're being
# throttled" -- used to route into the right PublisherError subclass so the
# worker can decide retry vs. wait-and-retry vs. give up (§5).
_AUTH_ERROR_CODES = {190}  # OAuthException: invalid/expired token
_RATE_LIMIT_ERROR_CODES = {4, 17, 32, 613}  # various Meta rate-limit codes


def _graph_url(path: str) -> str:
    return f"https://graph.facebook.com/{settings.GRAPH_API_VERSION}/{path}"


def _raise_for_graph_error(resp: httpx.Response) -> None:
    if resp.status_code < 400:
        return
    try:
        body = resp.json()
        err = body.get("error", {})
    except ValueError:
        err = {}
    code = err.get("code")
    message = err.get("message", resp.text[:500])

    if resp.status_code == 401 or code in _AUTH_ERROR_CODES:
        raise PublisherAuthError(message)
    if code in _RATE_LIMIT_ERROR_CODES or resp.status_code == 429:
        raise PublisherRateLimitError(message)
    if 500 <= resp.status_code < 600:
        raise PublisherTemporaryError(message)
    # Everything else from Meta (invalid media, policy rejection, bad
    # parameters) is treated as definitive -- §5 "erreur définitive".
    raise PublisherPermanentError(message)


class InstagramOfficialPublisher(SocialPublisher):
    def __init__(self, *, http_client: httpx.Client | None = None) -> None:
        self._client = http_client or httpx.Client(timeout=settings.GRAPH_API_TIMEOUT_SECONDS)

    # --- OAuth / connection -------------------------------------------------

    def connect_account(self, *, authorization_code: str) -> dict[str, Any]:
        if not settings.IG_APP_ID or not settings.IG_APP_SECRET or not settings.IG_OAUTH_REDIRECT_URI:
            raise PublisherPermanentError(
                "IG_APP_ID/IG_APP_SECRET/IG_OAUTH_REDIRECT_URI are not configured -- "
                "see README 'Instagram connection' (manual-token connect works without these)."
            )
        resp = self._client.get(
            _graph_url("oauth/access_token"),
            params={
                "client_id": settings.IG_APP_ID,
                "client_secret": settings.IG_APP_SECRET,
                "redirect_uri": settings.IG_OAUTH_REDIRECT_URI,
                "code": authorization_code,
            },
        )
        _raise_for_graph_error(resp)
        short_lived = resp.json()
        return self.refresh_connection(access_token=short_lived["access_token"])

    def refresh_connection(self, *, access_token: str) -> dict[str, Any]:
        """Exchange for a long-lived (60-day) token -- confirmed endpoint
        shape, see module docstring / plan research notes."""
        if not settings.IG_APP_ID or not settings.IG_APP_SECRET:
            raise PublisherPermanentError("IG_APP_ID/IG_APP_SECRET are not configured")
        resp = self._client.get(
            _graph_url("oauth/access_token"),
            params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.IG_APP_ID,
                "client_secret": settings.IG_APP_SECRET,
                "fb_exchange_token": access_token,
            },
        )
        _raise_for_graph_error(resp)
        return resp.json()  # {access_token, token_type, expires_in}

    def list_linked_instagram_accounts(self, *, access_token: str) -> list[dict[str, Any]]:
        """Resolve every Instagram Business Account reachable from this
        user token via their managed Facebook Pages -- one API call per
        Page is unavoidable with this flow (Graph API has no batch field
        for it across pages in one call)."""
        resp = self._client.get(_graph_url("me/accounts"), params={"access_token": access_token, "limit": 100})
        _raise_for_graph_error(resp)
        pages = resp.json().get("data", [])

        linked: list[dict[str, Any]] = []
        for page in pages:
            page_resp = self._client.get(
                _graph_url(page["id"]),
                params={"fields": "instagram_business_account", "access_token": page.get("access_token", access_token)},
            )
            if page_resp.status_code >= 400:
                continue  # page without a linked IG account, or no permission -- skip, don't abort the whole list
            ig_account = page_resp.json().get("instagram_business_account")
            if ig_account:
                linked.append(
                    {
                        "ig_business_id": ig_account["id"],
                        "page_id": page["id"],
                        "page_access_token": page.get("access_token"),
                    }
                )
        return linked

    def validate_account(self, *, ig_business_id: str, access_token: str) -> bool:
        resp = self._client.get(
            _graph_url(ig_business_id), params={"fields": "id,username", "access_token": access_token}
        )
        return resp.status_code < 400

    # --- Publishing -----------------------------------------------------

    def upload_media(
        self, *, ig_business_id: str, access_token: str, media_url: str, caption: str, dry_run: bool
    ) -> MediaContainer:
        if dry_run:
            raise RuntimeError("upload_media called with dry_run=True -- caller must short-circuit before reaching the publisher")
        if not settings.PUBLIC_BASE_URL:
            raise PublisherPermanentError(
                "PUBLIC_BASE_URL is not configured -- Instagram cannot fetch media from a non-public URL."
            )
        resp = self._client.post(
            _graph_url(f"{ig_business_id}/media"),
            data={
                "media_type": "REELS",
                "video_url": media_url,
                "caption": caption,
                "access_token": access_token,
            },
        )
        _raise_for_graph_error(resp)
        container_id = resp.json()["id"]
        return MediaContainer(container_id=container_id, status="IN_PROGRESS")

    def get_container_status(self, *, container_id: str, access_token: str) -> str:
        resp = self._client.get(
            _graph_url(container_id), params={"fields": "status_code", "access_token": access_token}
        )
        _raise_for_graph_error(resp)
        return resp.json().get("status_code", "UNKNOWN")

    def publish_post(
        self, *, ig_business_id: str, access_token: str, container: MediaContainer, dry_run: bool
    ) -> PublishResult:
        if dry_run:
            raise RuntimeError("publish_post called with dry_run=True -- caller must short-circuit before reaching the publisher")
        resp = self._client.post(
            _graph_url(f"{ig_business_id}/media_publish"),
            data={"creation_id": container.container_id, "access_token": access_token},
        )
        _raise_for_graph_error(resp)
        body = resp.json()
        return PublishResult(provider_post_id=body["id"], raw_response=body)

    def get_post_status(self, *, provider_post_id: str, access_token: str) -> dict[str, Any]:
        resp = self._client.get(
            _graph_url(provider_post_id), params={"fields": "id,permalink,timestamp", "access_token": access_token}
        )
        _raise_for_graph_error(resp)
        return resp.json()

    def cancel_post(self, *, container_id: str, access_token: str) -> None:
        # No-op by design -- see backend/publishers/base.py docstring: once
        # a container is FINISHED there's nothing to cancel on Instagram's
        # side; the only real "cancel" is never calling publish_post on it.
        return None
