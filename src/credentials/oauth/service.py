"""OAuth service orchestration for credentials upsert."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

from credentials import service as credentials_service
from credentials.schemas import ConnectionRecord
from credentials.oauth.exceptions import OAuthProviderError
from credentials.oauth.providers import google_ads, meta
from credentials.oauth.state import build_state_token, decode_state_token

_SUPPORTED_PROVIDERS = {"meta", "google_ads"}


def build_authorize_url(
    *,
    provider: str,
    tenant_id: str,
    user_id: str,
    connection_id: str,
    name: str | None = None,
) -> str:
    """Build provider-specific authorize URL with signed state."""

    provider_norm = _normalize_provider(provider)
    state_secret = _env_required("MDS_OAUTH_STATE_SECRET")
    state = build_state_token(
        secret=state_secret,
        tenant_id=tenant_id,
        connection_id=connection_id,
        provider=provider_norm,
        user_id=user_id,
        name=name,
    )
    if provider_norm == "meta":
        return meta.build_authorize_url(state=state)
    if provider_norm == "google_ads":
        return google_ads.build_authorize_url(state=state)
    raise OAuthProviderError(f"unsupported oauth provider '{provider}'")


async def handle_callback(
    *,
    provider: str,
    code: str,
    state: str,
) -> ConnectionRecord:
    """Exchange provider code and upsert credentials payload."""

    provider_norm = _normalize_provider(provider)
    state_secret = _env_required("MDS_OAUTH_STATE_SECRET")
    state_payload = decode_state_token(token=state, secret=state_secret)

    state_provider = str(state_payload["provider"]).strip()
    if state_provider != provider_norm:
        raise OAuthProviderError(
            f"provider mismatch between callback path '{provider_norm}' and state '{state_provider}'"
        )

    tenant_id = str(state_payload["tenant_id"]).strip()
    connection_id = str(state_payload["connection_id"]).strip()
    name = str(state_payload.get("name", "")).strip() or None

    if provider_norm == "meta":
        payload = await meta.exchange_code_for_tokens(code=code)
    elif provider_norm == "google_ads":
        token_payload = await google_ads.exchange_code_for_tokens(code=code)
        payload = {
            "client_id": _env_required("GOOGLE_OAUTH_CLIENT_ID"),
            "client_secret": _env_required("GOOGLE_OAUTH_CLIENT_SECRET"),
            "developer_token": _env_required("MDS_GOOGLE_ADS_DEVELOPER_TOKEN"),
            "refresh_token": token_payload["refresh_token"],
            "access_token": token_payload["access_token"],
            "token_type": token_payload.get("token_type", "Bearer"),
            "expires_in": token_payload.get("expires_in", 0),
        }
    else:
        raise OAuthProviderError(f"unsupported oauth provider '{provider}'")

    return credentials_service.upsert_connection(
        tenant_id=tenant_id,
        provider=provider_norm,
        connection_id=connection_id,
        payload=payload,
        name=name,
    )


def build_success_redirect_url(*, provider: str, connection_id: str) -> str:
    """Build frontend success URL after OAuth callback."""

    base = os.getenv(
        "MDS_OAUTH_FRONTEND_SUCCESS_URL",
        "http://localhost:3000/credentials-library",
    ).strip()
    params = urlencode(
        {
            "oauth": "success",
            "provider": _normalize_provider(provider),
            "connection_id": connection_id,
        }
    )
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{params}"


def _normalize_provider(provider: str) -> str:
    value = provider.strip().lower()
    if value not in _SUPPORTED_PROVIDERS:
        raise OAuthProviderError(
            f"unsupported oauth provider '{provider}'. expected one of {sorted(_SUPPORTED_PROVIDERS)}"
        )
    return value


def _env_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise OAuthProviderError(f"missing required env var '{name}'")
    return value

