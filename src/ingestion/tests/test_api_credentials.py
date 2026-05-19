"""API tests for tenant-scoped credentials endpoints."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from credentials.exceptions import SecretManagerError, SecretPayloadError
from credentials.secrets import build_secret_id
from credentials.tables import Base


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Create a TestClient with isolated credentials DB and mocked secrets."""

    db_path = tmp_path / "credentials_api.db"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    @contextmanager
    def _get_session():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    import credentials.service as credentials_service

    monkeypatch.setattr(credentials_service, "get_session", _get_session)
    monkeypatch.setattr(
        credentials_service,
        "store_connection_secret",
        lambda tenant_id, provider, connection_id, payload: build_secret_id(
            tenant_id, provider, connection_id
        ),
    )
    monkeypatch.setattr(
        credentials_service,
        "rotate_connection_secret",
        lambda tenant_id, provider, connection_id, payload: f"version-{connection_id}",
    )

    from fastapi.testclient import TestClient

    import api as api_module

    with TestClient(api_module.app) as client:
        yield client

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _headers(tenant_id: str) -> dict[str, str]:
    return {"X-Tenant-Id": tenant_id}


def _assert_request_id(response) -> None:
    request_id = response.headers.get("x-request-id")
    assert request_id, "X-Request-Id header missing"
    uuid.UUID(request_id)


def test_credentials_upsert_create_and_update(api_client) -> None:
    create = api_client.put(
        "/api/credentials/meta/conn-1",
        headers=_headers("tenant-a"),
        json={"payload": {"access_token": "a"}, "name": "Primary Meta"},
    )
    assert create.status_code == 200, create.text
    _assert_request_id(create)
    body = create.json()["connection"]
    assert body["connection_id"] == "conn-1"
    assert body["tenant_id"] == "tenant-a"
    assert body["provider"] == "meta"
    assert body["secret_id"] == "tenant-a-meta-conn-1"
    assert body["status"] == "active"
    assert body["name"] == "Primary Meta"

    update = api_client.put(
        "/api/credentials/meta/conn-1",
        headers=_headers("tenant-a"),
        json={"payload": {"access_token": "b"}, "name": "Meta Updated"},
    )
    assert update.status_code == 200, update.text
    _assert_request_id(update)
    assert update.json()["connection"]["name"] == "Meta Updated"

    listed = api_client.get("/api/credentials", headers=_headers("tenant-a"))
    assert listed.status_code == 200
    assert listed.json()["count"] == 1


def test_credentials_tenant_isolation(api_client) -> None:
    api_client.put(
        "/api/credentials/meta/conn-a",
        headers=_headers("tenant-a"),
        json={"payload": {"access_token": "a"}},
    )
    api_client.put(
        "/api/credentials/meta/conn-b",
        headers=_headers("tenant-b"),
        json={"payload": {"access_token": "b"}},
    )

    list_a = api_client.get("/api/credentials", headers=_headers("tenant-a"))
    list_b = api_client.get("/api/credentials", headers=_headers("tenant-b"))
    assert list_a.status_code == 200
    assert list_b.status_code == 200
    assert list_a.json()["count"] == 1
    assert list_b.json()["count"] == 1
    assert list_a.json()["connections"][0]["connection_id"] == "conn-a"
    assert list_b.json()["connections"][0]["connection_id"] == "conn-b"

    wrong_tenant = api_client.get(
        "/api/credentials/conn-a", headers=_headers("tenant-b")
    )
    assert wrong_tenant.status_code == 404
    assert wrong_tenant.json()["error"] == "connection_not_found"


def test_credentials_patch_status(api_client) -> None:
    api_client.put(
        "/api/credentials/meta/conn-status",
        headers=_headers("tenant-a"),
        json={"payload": {"access_token": "a"}},
    )
    patched = api_client.patch(
        "/api/credentials/conn-status/status",
        headers=_headers("tenant-a"),
        json={"status": "inactive"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["connection"]["status"] == "inactive"


def test_credentials_missing_tenant_header_returns_400(api_client) -> None:
    resp = api_client.put(
        "/api/credentials/meta/conn-1",
        json={"payload": {"access_token": "a"}},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "missing_tenant_header"
    _assert_request_id(resp)


def test_credentials_error_mapping_secret_payload(api_client, monkeypatch) -> None:
    import api as api_module

    def _raise(*args, **kwargs):
        raise SecretPayloadError("bad payload")

    monkeypatch.setattr(api_module.credentials_service, "upsert_connection", _raise)
    resp = api_client.put(
        "/api/credentials/meta/conn-error",
        headers=_headers("tenant-a"),
        json={"payload": {"access_token": "a"}},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_payload"


def test_credentials_error_mapping_secret_manager(api_client, monkeypatch) -> None:
    import api as api_module

    def _raise(*args, **kwargs):
        raise SecretManagerError("gcp unavailable")

    monkeypatch.setattr(api_module.credentials_service, "upsert_connection", _raise)
    resp = api_client.put(
        "/api/credentials/meta/conn-error2",
        headers=_headers("tenant-a"),
        json={"payload": {"access_token": "a"}},
    )
    assert resp.status_code == 502
    assert resp.json()["error"] == "secret_manager_failed"
