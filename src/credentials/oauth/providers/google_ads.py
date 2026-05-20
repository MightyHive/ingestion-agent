"""Google Ads OAuth provider helpers."""

from __future__ import annotations

import os
from urllib.parse import urlencode

import httpx

from credentials.oauth.exceptions import OAuthProviderError

_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_DEFAULT_SCOPE = "https://www.googleapis.com/auth/adwords"


def build_authorize_url(*, state: str) -> str:
    """Build Google OAuth authorize URL from env config."""

    client_id = _env_required("GOOGLE_OAUTH_CLIENT_ID")
    redirect_uri = _env_required("GOOGLE_OAUTH_REDIRECT_URI")
    scope = os.getenv("GOOGLE_OAUTH_SCOPE", _DEFAULT_SCOPE).strip() or _DEFAULT_SCOPE
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(*, code: str) -> dict[str, str | int]:
    """Exchange Google OAuth code for token payload."""

    client_id = _env_required("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = _env_required("GOOGLE_OAUTH_CLIENT_SECRET")
    redirect_uri = _env_required("GOOGLE_OAUTH_REDIRECT_URI")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "code": code,
                "grant_type": "authorization_code",
            },
        )

    if resp.status_code >= 400:
        raise OAuthProviderError(
            f"google token exchange failed ({resp.status_code}): {resp.text[:300]}"
        )

    payload = resp.json()
    refresh_token = str(payload.get("refresh_token", "")).strip()
    access_token = str(payload.get("access_token", "")).strip()
    if not refresh_token:
        raise OAuthProviderError(
            "google token exchange did not return refresh_token; "
            "ensure prompt=consent and access_type=offline"
        )
    if not access_token:
        raise OAuthProviderError("google token exchange did not return access_token")
    return {
        "refresh_token": refresh_token,
        "access_token": access_token,
        "token_type": str(payload.get("token_type", "Bearer")),
        "expires_in": int(payload.get("expires_in", 0)),
    }


def _env_required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise OAuthProviderError(f"missing required env var '{name}'")
    return value

