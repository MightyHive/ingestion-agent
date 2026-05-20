"""Unit tests for credentials secret storage helpers."""

from __future__ import annotations

import pytest

from credentials.exceptions import SecretPayloadError
from credentials.secrets import (
    build_secret_id,
    get_connection_secret,
    revoke_connection_secret,
    rotate_connection_secret,
    secret_resource_name,
    store_connection_secret,
)


class _FakeBackend:
    """Simple backend double to verify API behavior without network calls."""

    def __init__(self) -> None:
        self.ensure_calls: list[str] = []
        self.version_calls: list[tuple[str, bytes]] = []
        self.access_calls: list[tuple[str, str]] = []
        self.disable_calls: list[str] = []
        self.stored: dict[str, bytes] = {}
        self.disabled: set[str] = set()
        self._version = 0

    def ensure_secret(self, secret_id: str) -> None:
        self.ensure_calls.append(secret_id)

    def add_secret_version(self, secret_id: str, payload: bytes) -> str:
        self._version += 1
        self.version_calls.append((secret_id, payload))
        self.stored[secret_id] = payload
        return str(self._version)

    def access_secret_version(self, secret_id: str, version: str = "latest") -> bytes:
        self.access_calls.append((secret_id, version))
        if secret_id in self.disabled:
            raise KeyError(secret_id)
        return self.stored[secret_id]

    def disable_all_secret_versions(self, secret_id: str) -> int:
        self.disable_calls.append(secret_id)
        if secret_id in self.stored:
            self.disabled.add(secret_id)
            return 1
        return 0


def _patch_both_backends(monkeypatch: pytest.MonkeyPatch, fake: _FakeBackend) -> None:
    monkeypatch.setattr("credentials.secrets.get_writer_secrets_backend", lambda: fake)
    monkeypatch.setattr("credentials.secrets.get_reader_secrets_backend", lambda: fake)


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
    _patch_both_backends(monkeypatch, fake)

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
    _patch_both_backends(monkeypatch, fake)

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


def test_get_connection_secret_reads_and_decodes_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeBackend()
    _patch_both_backends(monkeypatch, fake)
    store_connection_secret(
        tenant_id="dev",
        provider="meta",
        connection_id="conn-1",
        payload={"access_token": "t1", "ad_account_id": "123"},
    )

    payload = get_connection_secret(
        tenant_id="dev",
        provider="meta",
        connection_id="conn-1",
    )
    assert payload == {"access_token": "t1", "ad_account_id": "123"}
    assert fake.access_calls == [("dev-meta-conn-1", "latest")]


def test_get_connection_secret_rejects_non_json_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeBackend()
    _patch_both_backends(monkeypatch, fake)
    store_connection_secret(
        tenant_id="dev",
        provider="meta",
        connection_id="conn-raw",
        payload="raw-token",
    )

    with pytest.raises(SecretPayloadError, match="JSON object"):
        get_connection_secret(
            tenant_id="dev",
            provider="meta",
            connection_id="conn-raw",
        )


def test_store_connection_secret_rejects_invalid_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Payload must be bytes, str, or JSON-serializable dict."""

    fake = _FakeBackend()
    _patch_both_backends(monkeypatch, fake)
    with pytest.raises(SecretPayloadError):
        store_connection_secret(
            tenant_id="dev",
            provider="meta",
            connection_id="bad",
            payload=123,  # type: ignore[arg-type]
        )


def test_revoke_connection_secret_disables_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeBackend()
    _patch_both_backends(monkeypatch, fake)
    store_connection_secret(
        tenant_id="dev",
        provider="meta",
        connection_id="revoke-1",
        payload={"access_token": "x"},
    )

    disabled = revoke_connection_secret(
        tenant_id="dev",
        provider="meta",
        connection_id="revoke-1",
    )
    assert disabled == 1
    assert fake.disable_calls == ["dev-meta-revoke-1"]
    with pytest.raises(KeyError):
        get_connection_secret(
            tenant_id="dev",
            provider="meta",
            connection_id="revoke-1",
        )


def test_store_uses_writer_and_get_uses_reader_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = _FakeBackend()
    reader = _FakeBackend()
    monkeypatch.setattr("credentials.secrets.get_writer_secrets_backend", lambda: writer)
    monkeypatch.setattr("credentials.secrets.get_reader_secrets_backend", lambda: reader)

    store_connection_secret(
        tenant_id="dev",
        provider="meta",
        connection_id="split-1",
        payload={"access_token": "tok"},
    )
    reader.stored["dev-meta-split-1"] = b'{"access_token":"tok"}'

    payload = get_connection_secret(
        tenant_id="dev",
        provider="meta",
        connection_id="split-1",
    )
    assert payload == {"access_token": "tok"}
    assert writer.ensure_calls == ["dev-meta-split-1"]
    assert reader.access_calls == [("dev-meta-split-1", "latest")]
    assert reader.ensure_calls == []


def test_secret_resource_name_builds_expected_path() -> None:
    """Resource helper should match Secret Manager naming format."""

    resource = secret_resource_name("monks-mds-dev", "dev-meta-abc")
    assert resource == "projects/monks-mds-dev/secrets/dev-meta-abc"
