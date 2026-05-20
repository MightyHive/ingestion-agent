"""Signed state helpers for OAuth callback correlation."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from typing import Any

from credentials.oauth.exceptions import InvalidOAuthStateError


def build_state_token(
    *,
    secret: str,
    tenant_id: str,
    connection_id: str,
    provider: str,
    user_id: str,
    name: str | None = None,
    ttl_seconds: int = 600,
) -> str:
    """Build state token signed with HMAC-SHA256."""

    exp = int((datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).timestamp())
    payload: dict[str, Any] = {
        "tenant_id": tenant_id,
        "connection_id": connection_id,
        "provider": provider,
        "user_id": user_id,
        "exp": exp,
        "nonce": secrets.token_urlsafe(12),
    }
    if name:
        payload["name"] = name
    return _encode_signed_payload(payload=payload, secret=secret)


def decode_state_token(*, token: str, secret: str) -> dict[str, Any]:
    """Decode and validate OAuth state token."""

    payload = _decode_signed_payload(token=token, secret=secret)
    exp = int(payload.get("exp", 0))
    now = int(datetime.now(timezone.utc).timestamp())
    if exp < now:
        raise InvalidOAuthStateError("oauth state has expired")
    required = ("tenant_id", "connection_id", "provider", "user_id")
    missing = [key for key in required if not str(payload.get(key, "")).strip()]
    if missing:
        raise InvalidOAuthStateError(
            f"oauth state is missing required fields: {', '.join(missing)}"
        )
    return payload


def _encode_signed_payload(*, payload: dict[str, Any], secret: str) -> str:
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    payload_b64 = _urlsafe_b64encode(payload_bytes)
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256)
    sig_b64 = _urlsafe_b64encode(sig.digest())
    return f"{payload_b64}.{sig_b64}"


def _decode_signed_payload(*, token: str, secret: str) -> dict[str, Any]:
    if "." not in token:
        raise InvalidOAuthStateError("oauth state format is invalid")
    payload_b64, sig_b64 = token.split(".", 1)
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256)
    expected_sig = _urlsafe_b64encode(sig.digest())
    if not hmac.compare_digest(sig_b64, expected_sig):
        raise InvalidOAuthStateError("oauth state signature mismatch")
    try:
        payload_bytes = _urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise InvalidOAuthStateError("oauth state payload is invalid") from exc
    if not isinstance(payload, dict):
        raise InvalidOAuthStateError("oauth state payload must be an object")
    return payload


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _urlsafe_b64decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))

