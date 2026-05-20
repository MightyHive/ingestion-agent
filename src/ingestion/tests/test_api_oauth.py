"""API tests for OAuth authorize/callback endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Build TestClient with tenant auth registry configured."""

    from fastapi.testclient import TestClient

    registry_path = tmp_path / "user_tenants.json"
    registry_path.write_text(
        json.dumps({"users": {"alice": ["tenant-a"]}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MDS_USER_TENANTS_FILE", str(registry_path))
    monkeypatch.setenv("MDS_OAUTH_STATE_SECRET", "test-secret")
    monkeypatch.delenv("MDS_AUTH_DISABLED", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import api as api_module

    with TestClient(api_module.app) as client:
        yield client


def test_oauth_authorize_requires_user(api_client) -> None:
    resp = api_client.get(
        "/api/oauth/meta/authorize",
        params={"connection_id": "conn-1"},
        headers={"X-Tenant-Id": "tenant-a"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "missing_user"


def test_oauth_authorize_redirects_when_allowed(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    import api as api_module

    monkeypatch.setattr(
        api_module.oauth_service,
        "build_authorize_url",
        lambda **kwargs: "https://provider.example/authorize",
    )
    resp = api_client.get(
        "/api/oauth/meta/authorize",
        params={"connection_id": "conn-1"},
        headers={"X-Tenant-Id": "tenant-a", "X-User-Id": "alice"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://provider.example/authorize"


def test_oauth_callback_redirects_on_success(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    import api as api_module

    class _Record:
        connection_id = "conn-1"

    async def _handle_callback(**kwargs):
        return _Record()

    monkeypatch.setattr(api_module.oauth_service, "handle_callback", _handle_callback)
    monkeypatch.setattr(
        api_module.oauth_service,
        "build_success_redirect_url",
        lambda **kwargs: "http://localhost:3000/cb?oauth=success",
    )

    resp = api_client.get(
        "/api/oauth/meta/callback",
        params={"code": "code-1", "state": "state-1"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "oauth=success" in resp.headers["location"]


def test_oauth_callback_returns_400_on_state_error(
    api_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    import api as api_module

    async def _handle_callback(**kwargs):
        raise api_module.InvalidOAuthStateError("bad state")

    monkeypatch.setattr(api_module.oauth_service, "handle_callback", _handle_callback)
    resp = api_client.get(
        "/api/oauth/meta/callback",
        params={"code": "code-1", "state": "state-1"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_oauth_state"

