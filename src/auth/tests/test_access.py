"""Unit tests for tenant authorization helpers."""

from __future__ import annotations

import pytest

from auth.access import assert_tenant_allowed, resolve_user_id
from auth.exceptions import (
    InvalidApiKeyError,
    MissingUserError,
    TenantAccessDeniedError,
    UnknownUserError,
)
from auth.registry import UserTenantRegistry


def _registry() -> UserTenantRegistry:
    return UserTenantRegistry(
        users={"alice": frozenset({"tenant-a"}), "bob": frozenset({"tenant-b"})},
        api_keys={"key-alice": "alice"},
    )


def test_resolve_user_id_from_header() -> None:
    user_id = resolve_user_id(
        x_user_id="alice",
        authorization=None,
        registry=_registry(),
    )
    assert user_id == "alice"


def test_resolve_user_id_from_api_key() -> None:
    user_id = resolve_user_id(
        x_user_id=None,
        authorization="Bearer key-alice",
        registry=_registry(),
    )
    assert user_id == "alice"


def test_resolve_user_id_invalid_api_key() -> None:
    with pytest.raises(InvalidApiKeyError):
        resolve_user_id(
            x_user_id=None,
            authorization="Bearer unknown",
            registry=_registry(),
        )


def test_resolve_user_id_missing_identity() -> None:
    with pytest.raises(MissingUserError):
        resolve_user_id(
            x_user_id=None,
            authorization=None,
            registry=_registry(),
        )


def test_assert_tenant_allowed_allows_registered_pair() -> None:
    assert_tenant_allowed(user_id="alice", tenant_id="tenant-a", registry=_registry())


def test_assert_tenant_allowed_unknown_user() -> None:
    with pytest.raises(UnknownUserError):
        assert_tenant_allowed(user_id="charlie", tenant_id="tenant-a", registry=_registry())


def test_assert_tenant_allowed_forbidden_tenant() -> None:
    with pytest.raises(TenantAccessDeniedError):
        assert_tenant_allowed(user_id="alice", tenant_id="tenant-b", registry=_registry())

