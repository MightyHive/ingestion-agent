"""Registry loader for user -> tenant authorization mappings."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path


@dataclass(frozen=True)
class UserTenantRegistry:
    """In-memory representation of the authorization registry."""

    users: dict[str, frozenset[str]]
    api_keys: dict[str, str]


def load_user_tenant_registry(path: str | None = None) -> UserTenantRegistry:
    """Load registry from JSON file configured for local/dev authorization."""

    registry_path = _resolve_registry_path(path)
    if not registry_path.exists():
        return UserTenantRegistry(users={}, api_keys={})

    raw = json.loads(registry_path.read_text(encoding="utf-8"))
    users_raw = raw.get("users", {})
    api_keys_raw = raw.get("api_keys", {})

    users: dict[str, frozenset[str]] = {}
    for user_id, tenant_ids in users_raw.items():
        if not isinstance(user_id, str):
            continue
        if not isinstance(tenant_ids, list):
            continue
        normalized = [str(item).strip() for item in tenant_ids if str(item).strip()]
        users[user_id.strip()] = frozenset(normalized)

    api_keys: dict[str, str] = {}
    for key, user_id in api_keys_raw.items():
        key_value = str(key).strip()
        user_value = str(user_id).strip()
        if key_value and user_value:
            api_keys[key_value] = user_value

    return UserTenantRegistry(users=users, api_keys=api_keys)


def _resolve_registry_path(path: str | None = None) -> Path:
    if path:
        return Path(path).expanduser().resolve()
    env_path = os.getenv("MDS_USER_TENANTS_FILE", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    return Path("~/.mds/user_tenants.json").expanduser().resolve()

