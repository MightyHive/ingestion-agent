"""Helpers to resolve user identity and tenant authorization."""

from __future__ import annotations

import os

from auth.exceptions import (
    InvalidApiKeyError,
    MissingUserError,
    TenantAccessDeniedError,
    UnknownUserError,
)
from auth.registry import UserTenantRegistry


def auth_is_disabled() -> bool:
    """Return whether tenant authorization checks are explicitly disabled."""

    value = os.getenv("MDS_AUTH_DISABLED", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def resolve_user_id(
    *,
    x_user_id: str | None,
    authorization: str | None,
    registry: UserTenantRegistry,
) -> str:
    """Resolve request identity from X-User-Id or Bearer api key."""

    header_user = (x_user_id or "").strip()
    if header_user:
        return header_user

    token = _extract_bearer_token(authorization)
    if token:
        user_id = registry.api_keys.get(token)
        if not user_id:
            raise InvalidApiKeyError("invalid bearer API key")
        return user_id

    raise MissingUserError("missing X-User-Id or Authorization Bearer token")


def assert_tenant_allowed(
    *,
    user_id: str,
    tenant_id: str,
    registry: UserTenantRegistry,
) -> None:
    """Raise when user is unknown or not allowed to access tenant."""

    allowed = registry.users.get(user_id)
    if allowed is None:
        raise UnknownUserError(f"user '{user_id}' is not registered")
    if tenant_id not in allowed:
        raise TenantAccessDeniedError(
            f"user '{user_id}' is not allowed to access tenant '{tenant_id}'"
        )


def _extract_bearer_token(authorization: str | None) -> str | None:
    header_value = (authorization or "").strip()
    if not header_value:
        return None
    parts = header_value.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None

