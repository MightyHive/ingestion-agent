"""Meta OAuth provider helpers."""

from __future__ import annotations

import os
from urllib.parse import urlencode

import httpx

from credentials.oauth.exceptions import OAuthProviderError

_AUTHORIZE_URL = "https://www.facebook.com/v20.0/dialog/oauth"
_TOKEN_URL = "https://graph.facebook.com/v20.0/oauth/access_token"
_DEFAULT_SCOPE = "ads_read,read_insights"


def build_authorize_url(*, state: str) -> str:
    """Build Meta OAuth authorize URL from env config."""

    app_id = _env_required("META_APP_ID")
    redirect_uri = _env_required("META_OAUTH_REDIRECT_URI")
    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": os.getenv("META_OAUTH_SCOPE", _DEFAULT_SCOPE).strip() or _DEFAULT_SCOPE,
        "state": state,
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(*, code: str) -> dict[str, str | int]:
    """Exchange Meta OAuth code for access token payload."""

    app_id = _env_required("META_APP_ID")
    app_secret = _env_required("META_APP_SECRET")
    redirect_uri = _env_required("META_OAUTH_REDIRECT_URI")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            _TOKEN_URL,
            params={
                "client_id": app_id,
                "client_secret": app_secret,
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )

    if resp.status_code >= 400:
        raise OAuthProviderError(
            f"meta token exchange failed ({resp.status_code}): {resp.text[:300]}"
        )

    payload = resp.json()
    access_token = str(payload.get("access_token", "")).strip()
    if not access_token:
        raise OAuthProviderError("meta token exchange did not return access_token")
    token_type = str(payload.get("token_type", "bearer")).strip() or "bearer"
    expires_in = int(payload.get("expires_in", 0))
    return {
        "access_token": access_token,
        "token_type": token_type,
        "expires_in": expires_in,
    }


def _env_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise OAuthProviderError(f"missing required env var '{name}'")
    return value

