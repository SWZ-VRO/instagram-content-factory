"""
Domain exceptions for the allocation/reservation path (§24). The 30-day
calendar generator (Phase 4) is expected to catch every one of these per
candidate and SKIP to the next variant/slot rather than let a single
failure abort the whole run -- exactly as §24 specifies.
"""


class ReservationError(Exception):
    """Base class for every reason a reservation attempt can be refused."""


class VariantNotFound(ReservationError):
    pass


class VariantNotAvailable(ReservationError):
    """Variant is not AVAILABLE (already MISSING_CAPTION/RESERVED/SCHEDULED/
    PUBLISHED/FAILED). Covers §24 checks 1-4 and the core rule in §2."""


class VariantAlreadyReserved(ReservationError):
    """Raised when the DB's partial unique index rejects the insert because
    another transaction won the race for this variant between our read and
    our write (§48 Test 7). The app-level status check is the fast path;
    this is the actual guarantee."""


class MissingCaptionError(ReservationError):
    """§13 -- a variant without a caption can never be scheduled."""


class AccountNotActiveError(ReservationError):
    pass


class MasterCooldownViolation(ReservationError):
    """§6 -- same master used on the same account within MIN_MASTER_GAP_DAYS."""
