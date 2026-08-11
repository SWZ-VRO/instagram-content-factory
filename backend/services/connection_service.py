"""
Account connection (§9, §17): two paths, converging on the same storage.

  - `connect_manual`: paste a long-lived token + IG Business Account id
    (obtained via Meta's own Graph API Explorer). Works today, with no
    IG_APP_ID/SECRET and no Meta App Review wait -- the pragmatic way to
    get real accounts connected while the full OAuth app review is pending.
  - `handle_oauth_callback` / `oauth_authorize_url`: the "Connect Instagram"
    button flow (§9), needs IG_APP_ID/IG_APP_SECRET/IG_OAUTH_REDIRECT_URI
    configured (a registered, reviewed Meta Developer App).

Both end up calling repositories.account_connection_repo (token encrypted
at rest, §53) and setting Account.ig_business_id/connection_status.
"""
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.account import Account
from backend.models.enums import ConnectionStatus
from backend.publishers.exceptions import PublisherError
from backend.publishers.instagram_official import InstagramOfficialPublisher
from backend.repositories import account_connection_repo, account_repo


class AccountConnectionError(Exception):
    pass


def new_oauth_state() -> str:
    return secrets.token_urlsafe(24)


def oauth_authorize_url(*, state: str) -> str:
    if not settings.IG_APP_ID or not settings.IG_OAUTH_REDIRECT_URI:
        raise AccountConnectionError(
            "IG_APP_ID/IG_OAUTH_REDIRECT_URI are not configured -- see README 'Instagram connection' "
            "(connect_manual works without them)"
        )
    params = {
        "client_id": settings.IG_APP_ID,
        "redirect_uri": settings.IG_OAUTH_REDIRECT_URI,
        # Scope names per Facebook Login for Business -- reconfirm against
        # current Meta docs before relying on this (see module docstring
        # in backend/publishers/instagram_official.py).
        "scope": "instagram_business_basic,instagram_business_content_publish",
        "response_type": "code",
        "state": state,
    }
    return f"https://www.facebook.com/{settings.GRAPH_API_VERSION}/dialog/oauth?{urlencode(params)}"


def connect_manual(
    db: Session,
    *,
    account_id,
    ig_business_id: str,
    access_token_plain: str,
    publisher: InstagramOfficialPublisher | None = None,
) -> Account:
    account = account_repo.get(db, account_id)
    if account is None:
        raise AccountConnectionError(f"account {account_id} not found")

    publisher = publisher or InstagramOfficialPublisher()
    if not publisher.validate_account(ig_business_id=ig_business_id, access_token=access_token_plain):
        raise AccountConnectionError("token/ig_business_id could not be validated against the Graph API")

    account.ig_business_id = ig_business_id
    account.connection_status = ConnectionStatus.CONNECTED
    account.token_expires_at = None  # unknown for a manually-pasted token -- treat as "verify periodically"
    db.commit()

    account_connection_repo.store_token(db, account_id=account.id, access_token_plain=access_token_plain, expires_at=None)
    return account


def handle_oauth_callback(
    db: Session, *, authorization_code: str, publisher: InstagramOfficialPublisher | None = None
) -> list[Account]:
    """Exchanges the code, discovers every Instagram Business Account
    reachable from it (via the user's Facebook Pages), and upserts one
    Account row per one found. Returns the accounts connected/updated."""
    publisher = publisher or InstagramOfficialPublisher()
    try:
        token_data = publisher.connect_account(authorization_code=authorization_code)
        access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in")
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in) if expires_in else None
        linked = publisher.list_linked_instagram_accounts(access_token=access_token)
    except PublisherError as exc:
        raise AccountConnectionError(str(exc)) from exc

    if not linked:
        raise AccountConnectionError("no Instagram Business/Creator account found on any Facebook Page for this user")

    connected: list[Account] = []
    for entry in linked:
        token_for_account = entry.get("page_access_token") or access_token
        account = account_repo.get_by_ig_business_id(db, entry["ig_business_id"])
        if account is None:
            account = account_repo.create(db, username=f"ig_{entry['ig_business_id']}")
            account.ig_business_id = entry["ig_business_id"]
        account.page_id = entry.get("page_id")
        account.connection_status = ConnectionStatus.CONNECTED
        account.token_expires_at = expires_at
        db.commit()

        account_connection_repo.store_token(
            db, account_id=account.id, access_token_plain=token_for_account, expires_at=expires_at
        )
        connected.append(account)

    return connected
