"""
backend/services/storage.py -- LocalStorage is a trivial passthrough;
SupabaseStorage is tested with a mocked httpx client so these tests never
make a real network call (no live Supabase project in this environment).
"""
import pytest

from backend.core.config import settings
from backend.services import storage as storage_module
from backend.services.storage import LocalStorage, StorageError, SupabaseStorage, get_storage


def test_local_storage_is_a_passthrough(tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"x")
    result = LocalStorage().upload(f, remote_key="variants/whatever.mp4")
    assert result == str(f)


def test_get_storage_defaults_to_local():
    assert isinstance(get_storage(), LocalStorage)


def test_get_storage_returns_supabase_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "supabase")
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://xyz.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "test-key")
    assert isinstance(get_storage(), SupabaseStorage)


def test_supabase_storage_requires_credentials(monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_URL", "")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "")
    with pytest.raises(StorageError):
        SupabaseStorage()


class _FakeResponse:
    def __init__(self, status_code, text="", json_data=None):
        self.status_code = status_code
        self.text = text
        self._json = json_data or {}

    def json(self):
        return self._json


class _FakeHttpxClient:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._response


def test_supabase_upload_returns_public_url(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://xyz.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "test-key")
    monkeypatch.setattr(settings, "SUPABASE_STORAGE_BUCKET", "content")

    f = tmp_path / "MASTER_001_V01.mp4"
    f.write_bytes(b"fake video bytes")

    fake_client = _FakeHttpxClient(_FakeResponse(200))
    store = SupabaseStorage(http_client=fake_client)
    url = store.upload(f, remote_key="variants/MASTER_001_V01.mp4")

    assert url == "https://xyz.supabase.co/storage/v1/object/public/content/variants/MASTER_001_V01.mp4"
    assert len(fake_client.calls) == 1
    called_url, kwargs = fake_client.calls[0]
    assert called_url == "https://xyz.supabase.co/storage/v1/object/content/variants/MASTER_001_V01.mp4"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    # Never send tokens/keys anywhere except the Authorization/apikey headers.
    assert "test-key" not in called_url


def test_supabase_upload_raises_on_error_response(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://xyz.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_KEY", "test-key")

    f = tmp_path / "clip.mp4"
    f.write_bytes(b"x")

    fake_client = _FakeHttpxClient(_FakeResponse(403, text="not authorized"))
    store = SupabaseStorage(http_client=fake_client)
    with pytest.raises(StorageError):
        store.upload(f, remote_key="variants/clip.mp4")
