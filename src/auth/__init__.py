"""Authorization helpers for tenant-scoped API access."""

from auth.access import assert_tenant_allowed, auth_is_disabled, resolve_user_id
from auth.exceptions import (
    AuthError,
    InvalidApiKeyError,
    MissingUserError,
    TenantAccessDeniedError,
    UnknownUserError,
)
from auth.registry import UserTenantRegistry, load_user_tenant_registry

__all__ = [
    "assert_tenant_allowed",
    "auth_is_disabled",
    "resolve_user_id",
    "AuthError",
    "InvalidApiKeyError",
    "MissingUserError",
    "TenantAccessDeniedError",
    "UnknownUserError",
    "UserTenantRegistry",
    "load_user_tenant_registry",
]

