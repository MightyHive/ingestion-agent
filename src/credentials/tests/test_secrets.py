"""Unit tests for credentials secret storage helpers."""

from __future__ import annotations

import pytest

from credentials.exceptions import SecretPayloadError
from credentials.secrets import build_secret_id, rotate_connection_secret, secret_resource_name, store_connection_secret


class _FakeBackend:
    """Simple backend double to verify API behavior without network calls."""

    def __init__(self) -> None:
        self.ensure_calls: list[str] = []
        self.version_calls: list[tuple[str, bytes]] = []
        self._version = 0

    def ensure_secret(self, secret_id: str) -> None:
        self.ensure_calls.append(secret_id)

    def add_secret_version(self, secret_id: str, payload: bytes) -> str:
        self._version += 1
        self.version_calls.append((secret_id, payload))
        return str(self._version)


def test_build_secret_id_sanitizes_segments() -> None:
    """Secret ids should be stable and compatible with backend naming rules."""

    secret_id = build_secret_id(
        tenant_id="Tenant A",
        provider="Meta Ads",
        connection_id="id:123",
    )
    assert secret_id == "tenant-a-meta-ads-id-123"


def test_store_connection_secret_ensures_secret_and_writes_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Store should ensure secret existence and write a first version."""

    fake = _FakeBackend()
    monkeypatch.setattr("credentials.secrets.get_secrets_backend", lambda: fake)

    secret_id = store_connection_secret(
        tenant_id="dev",
        provider="meta",
        connection_id="abc-123",
        payload={"access_token": "token-a"},
    )
    assert secret_id == "dev-meta-abc-123"
    assert fake.ensure_calls == [secret_id]
    assert fake.version_calls == [
        (secret_id, b'{"access_token":"token-a"}'),
    ]


def test_rotate_connection_secret_returns_backend_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rotate should write a version and return backend version identifier."""

    fake = _FakeBackend()
    monkeypatch.setattr("credentials.secrets.get_secrets_backend", lambda: fake)

    store_connection_secret(
        tenant_id="dev",
        provider="meta",
        connection_id="rotate-1",
        payload="first",
    )
    version = rotate_connection_secret(
        tenant_id="dev",
        provider="meta",
        connection_id="rotate-1",
        payload="second",
    )
    assert version == "2"
    assert fake.version_calls[-1] == ("dev-meta-rotate-1", b"second")


def test_store_connection_secret_rejects_invalid_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Payload must be bytes, str, or JSON-serializable dict."""

    fake = _FakeBackend()
    monkeypatch.setattr("credentials.secrets.get_secrets_backend", lambda: fake)
    with pytest.raises(SecretPayloadError):
        store_connection_secret(
            tenant_id="dev",
            provider="meta",
            connection_id="bad",
            payload=123,  # type: ignore[arg-type]
        )


def test_secret_resource_name_builds_expected_path() -> None:
    """Resource helper should match Secret Manager naming format."""

    resource = secret_resource_name("monks-mds-dev", "dev-meta-abc")
    assert resource == "projects/monks-mds-dev/secrets/dev-meta-abc"
