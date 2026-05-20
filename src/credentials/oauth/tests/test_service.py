"""Unit tests for OAuth service orchestration."""

from __future__ import annotations

import asyncio

import pytest

from credentials.oauth import service as oauth_service


def test_handle_callback_meta_upserts_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MDS_OAUTH_STATE_SECRET", "secret-1")

    from credentials.oauth.state import build_state_token

    state_token = build_state_token(
        secret="secret-1",
        tenant_id="tenant-a",
        connection_id="conn-1",
        provider="meta",
        user_id="alice",
        name="Meta Connection",
    )

    async def _exchange_code(code: str):
        return {"access_token": "token-1", "token_type": "bearer", "expires_in": 3600}

    monkeypatch.setattr(oauth_service.meta, "exchange_code_for_tokens", _exchange_code)
    calls: list[dict] = []

    class _Record:
        connection_id = "conn-1"

    def _upsert(**kwargs):
        calls.append(kwargs)
        return _Record()

    monkeypatch.setattr(oauth_service.credentials_service, "upsert_connection", _upsert)

    record = asyncio.run(
        oauth_service.handle_callback(
            provider="meta",
            code="code-1",
            state=state_token,
        )
    )
    assert record.connection_id == "conn-1"
    assert calls[0]["tenant_id"] == "tenant-a"
    assert calls[0]["provider"] == "meta"
    assert calls[0]["connection_id"] == "conn-1"
    assert calls[0]["name"] == "Meta Connection"
    assert calls[0]["payload"]["access_token"] == "token-1"


def test_build_success_redirect_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MDS_OAUTH_FRONTEND_SUCCESS_URL", "http://localhost:3000/cb")
    url = oauth_service.build_success_redirect_url(
        provider="google_ads",
        connection_id="conn-123",
    )
    assert "oauth=success" in url
    assert "provider=google_ads" in url
    assert "connection_id=conn-123" in url

