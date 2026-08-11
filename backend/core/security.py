"""
Token-at-rest encryption. Instagram access tokens are never stored in plain
text (§53) and never logged. We derive a Fernet key from SECRET_KEY so
operators only manage one secret.

NOTE: rotating SECRET_KEY invalidates every stored token -- accounts would
need to be reconnected. That trade-off is intentional and documented in the
README; a KMS-backed multi-key scheme can replace this later without
touching callers (they only ever see encrypt_token/decrypt_token).
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from backend.core.config import settings


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_derive_fernet_key(settings.SECRET_KEY))


def encrypt_token(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_token(ciphertext: str) -> str:
    try:
        return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt stored token (wrong SECRET_KEY?)") from exc
