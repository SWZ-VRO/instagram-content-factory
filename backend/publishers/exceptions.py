"""
Publisher error taxonomy -- this is what lets the Publishing Worker (§5)
decide whether a failed post can go back to being retried, or must be
marked FAILED for good.
"""


class PublisherError(Exception):
    """Base class. Carries the raw provider response when available, but
    NEVER the access token -- callers must not log/store tokens (§53)."""


class PublisherAuthError(PublisherError):
    """Token invalid/expired/revoked (§17 ACCOUNT_AUTH_ERROR). The post
    itself is NOT abandoned -- it stays SCHEDULED, waiting for the account
    to be reconnected, per §17 ("mises en attente sans être perdues")."""


class PublisherRateLimitError(PublisherError):
    """Provider rate limit hit (§20/§35 RATE_LIMIT). Always retryable with
    backoff -- never a reason to fail the post outright."""


class PublisherTemporaryError(PublisherError):
    """Network error, provider 5xx, timeout, etc. (§5 "échec avant
    publication" -- upload failed / network error / provider temporary
    error). Retryable up to MAX_PUBLISH_ATTEMPTS."""


class PublisherPermanentError(PublisherError):
    """§5 "erreur définitive": invalid media, content policy rejection,
    account no longer eligible. Never retried -- goes straight to FAILED."""
