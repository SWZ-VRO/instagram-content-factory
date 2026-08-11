"""
Account connection (§9, §17). Uses a FakePublisher so nothing here makes a
real network call to Meta -- there is no live Meta app/credentials in this
environment (see README "Instagram connection").
"""
import pytest

from backend.models.enums import ConnectionStatus
from backend.publishers.base import SocialPublisher
from backend.services import connection_service
from tests.factories import make_account


class FakePublisher(SocialPublisher):
    def __init__(self, *, valid=True):
        self.valid = valid
        self.validate_calls = []

    def connect_account(self, *, authorization_code):
        raise NotImplementedError

    def validate_account(self, *, ig_business_id, access_token):
        self.validate_calls.append((ig_business_id, access_token))
        return self.valid

    def refresh_connection(self, *, access_token):
        raise NotImplementedError

    def upload_media(self, **kwargs):
        raise NotImplementedError

    def get_container_status(self, **kwargs):
        raise NotImplementedError

    def publish_post(self, **kwargs):
        raise NotImplementedError

    def get_post_status(self, **kwargs):
        raise NotImplementedError

    def cancel_post(self, **kwargs):
        return None


def test_connect_manual_succeeds_and_encrypts_the_token(db):
    account = make_account(db, username="ig001")
    publisher = FakePublisher(valid=True)

    updated = connection_service.connect_manual(
        db, account_id=account.id, ig_business_id="17800000000000000", access_token_plain="secret-token-value", publisher=publisher
    )

    assert updated.ig_business_id == "17800000000000000"
    assert updated.connection_status == ConnectionStatus.CONNECTED
    assert publisher.validate_calls == [("17800000000000000", "secret-token-value")]

    from backend.repositories import account_connection_repo

    connection = account_connection_repo.get_latest(db, account.id)
    assert connection is not None
    assert "secret-token-value" not in connection.access_token_encrypted  # never stored in plain text -- §53
    assert account_connection_repo.get_decrypted_token(db, account.id) == "secret-token-value"


def test_connect_manual_rejects_invalid_token_without_storing_it(db):
    account = make_account(db, username="ig002")
    publisher = FakePublisher(valid=False)

    with pytest.raises(connection_service.AccountConnectionError):
        connection_service.connect_manual(
            db, account_id=account.id, ig_business_id="1", access_token_plain="bad-token", publisher=publisher
        )

    from backend.repositories import account_connection_repo

    assert account_connection_repo.get_latest(db, account.id) is None


def test_connect_manual_checks_account_exists_before_calling_publisher(db):
    """A network call to Meta is wasted work (and a real HTTP request) if
    the account doesn't even exist locally -- must be checked first."""
    import uuid

    publisher = FakePublisher(valid=True)
    with pytest.raises(connection_service.AccountConnectionError):
        connection_service.connect_manual(
            db, account_id=uuid.uuid4(), ig_business_id="1", access_token_plain="x", publisher=publisher
        )
    assert publisher.validate_calls == []


def test_oauth_authorize_url_requires_app_credentials(db):
    with pytest.raises(connection_service.AccountConnectionError):
        connection_service.oauth_authorize_url(state="abc")


def test_oauth_authorize_url_builds_expected_dialog_url(monkeypatch):
    from backend.core.config import settings

    monkeypatch.setattr(settings, "IG_APP_ID", "123456")
    monkeypatch.setattr(settings, "IG_OAUTH_REDIRECT_URI", "https://example.test/callback")

    url = connection_service.oauth_authorize_url(state="my-state")
    assert url.startswith("https://www.facebook.com/")
    assert "client_id=123456" in url
    assert "state=my-state" in url
    assert "instagram_business_content_publish" in url
