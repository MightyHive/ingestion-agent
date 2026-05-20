"""Unit tests for user tenant registry loader."""

from __future__ import annotations

import json

from auth.registry import load_user_tenant_registry


def test_load_user_tenant_registry_reads_users_and_api_keys(tmp_path) -> None:
    registry_file = tmp_path / "user_tenants.json"
    registry_file.write_text(
        json.dumps(
            {
                "users": {"alice": ["tenant-a", "tenant-b"], "bob": ["tenant-c"]},
                "api_keys": {"dev-key-1": "alice"},
            }
        ),
        encoding="utf-8",
    )
    registry = load_user_tenant_registry(str(registry_file))
    assert registry.users["alice"] == {"tenant-a", "tenant-b"}
    assert registry.users["bob"] == {"tenant-c"}
    assert registry.api_keys["dev-key-1"] == "alice"


def test_load_user_tenant_registry_missing_file_returns_empty(tmp_path) -> None:
    registry = load_user_tenant_registry(str(tmp_path / "missing.json"))
    assert registry.users == {}
    assert registry.api_keys == {}

