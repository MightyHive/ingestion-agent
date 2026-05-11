"""TenantContext — multi-tenant configuration resolver.

Each MDS client lives in a separate GCP project. The dispatcher cannot
simply read a single global service account because:

* Cloud Function URLs are per-tenant.
* Connector secrets (e.g. Meta access token) live in the tenant's own
  Secret Manager.
* Audit logs must show the tenant SA, not MDS's.

This module is the **single point of truth** for "everything we need to
know about a given tenant before we can invoke a connector for them".

Phase 2 implementation (this file)
----------------------------------
Stub backed by a local JSON file. We are not going to ship Secret
Manager code until Phase 5; the stub exists so the rest of the graph
can be wired and tested deterministically.

Loader resolution order:

1. Path passed explicitly to :class:`TenantContext.resolve(...)`.
2. ``MDS_TENANTS_FILE`` environment variable.
3. ``~/.mds/tenants.json``.
4. Empty registry → ``UnknownTenantError``.

Expected file shape::

    {
      "tenants": {
        "demo-tenant": {
          "gcp_project": "monks-mds-demo",
          "service_account": "mds-runner@monks-mds-demo.iam.gserviceaccount.com",
          "context": {
            "ad_account_id": "123456789",
            "access_token": "EAAG..."
          }
        }
      }
    }

In Phase 5 ``context`` becomes a list of Secret Manager pointers
resolved at runtime; for now we just hand the dictionary to the
dispatcher.

Phase 5+ implementation (deferred)
----------------------------------
* Resolve ``service_account`` via
  :class:`google.auth.impersonated_credentials.Credentials`.
* Read each entry of ``auth.secrets`` from
  ``projects/{gcp_project}/secrets/{secret_id}/versions/{version}``.
* Cache resolved contexts per ``tenant_id`` for the lifetime of a
  request, never across requests (tokens may rotate).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

DEFAULT_TENANTS_PATH = Path("~/.mds/tenants.json").expanduser()


class TenantConfigError(Exception):
    """Raised when the local tenants file is missing or malformed."""


class UnknownTenantError(KeyError):
    """Raised when a tenant_id is not present in the registry."""


class MissingContextKeyError(KeyError):
    """Raised when the manifest requires a context key the tenant did not provide."""


@dataclass(frozen=True)
class TenantContext:
    """Resolved tenant information ready for a single connector invocation.

    Attributes
    ----------
    tenant_id:
        Stable identifier for the client (matches the registry key).
    gcp_project:
        Tenant's GCP project id. Used by the Cloud Function URL builder
        and by Secret Manager lookups in Phase 5.
    service_account:
        Email of the tenant SA we will impersonate in Phase 5+. Stored
        for trace clarity even though Phase 2 doesn't use it.
    context:
        Free-form dict of credentials/config the connector's ``fetch``
        function expects. The dispatcher injects this into the second
        positional arg of ``fetch(params, context)``.
    """

    tenant_id: str
    gcp_project: str
    service_account: str
    context: dict[str, Any] = field(default_factory=dict)

    def assert_satisfies(self, required_keys: list[str]) -> None:
        """Raise ``MissingContextKeyError`` if any required key is absent.

        Called by the dispatcher right before invoking the connector.
        Keys come from ``manifest.auth.context_required``.
        """
        missing = [k for k in required_keys if k not in self.context]
        if missing:
            raise MissingContextKeyError(
                f"tenant '{self.tenant_id}' is missing context keys: {missing!r}"
            )

    @classmethod
    def resolve(
        cls,
        tenant_id: str,
        *,
        path: Path | str | None = None,
    ) -> "TenantContext":
        """Resolve a tenant from the local registry (Phase 2 stub).

        See module docstring for resolution order.
        """
        loader = _get_loader_override()
        if loader is not None:
            ctx = loader(tenant_id)
            if ctx is None:
                raise UnknownTenantError(
                    f"tenant '{tenant_id}' not registered (test override)"
                )
            return ctx

        registry = _load_registry(path)
        entry = registry.get(tenant_id)
        if entry is None:
            raise UnknownTenantError(
                f"tenant '{tenant_id}' not in tenants file. "
                f"Known: {sorted(registry.keys())!r}"
            )
        try:
            return cls(
                tenant_id=tenant_id,
                gcp_project=str(entry["gcp_project"]),
                service_account=str(entry.get("service_account", "")),
                context=dict(entry.get("context", {}) or {}),
            )
        except KeyError as exc:
            raise TenantConfigError(
                f"tenant '{tenant_id}' is missing required key {exc!s}"
            ) from exc


def _resolve_path(path: Path | str | None) -> Path:
    if path is not None:
        return Path(path).expanduser()
    env_path = os.environ.get("MDS_TENANTS_FILE")
    if env_path:
        return Path(env_path).expanduser()
    return DEFAULT_TENANTS_PATH


def _load_registry(path: Path | str | None) -> dict[str, dict[str, Any]]:
    """Read and parse the tenants file. Returns ``{tenant_id: entry}``."""
    resolved = _resolve_path(path)
    if not resolved.exists():
        raise TenantConfigError(
            f"tenants file not found at {resolved}. "
            f"Set MDS_TENANTS_FILE or create ~/.mds/tenants.json. "
            f"See src/ingestion/auth/tenant_context.py docstring."
        )
    try:
        with resolved.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise TenantConfigError(
            f"tenants file at {resolved} is not valid JSON: {exc}"
        ) from exc
    tenants = data.get("tenants")
    if not isinstance(tenants, dict):
        raise TenantConfigError(
            f"tenants file at {resolved} must have a top-level 'tenants' object"
        )
    return tenants


# ---------------------------------------------------------------------------
# Test override hook
# ---------------------------------------------------------------------------
# Tests need to inject a TenantContext without hitting the filesystem.
# We expose a single overrideable callable so the resolution pipeline
# stays simple for production callers.

_LOADER_OVERRIDE: Optional[Callable[[str], Optional["TenantContext"]]] = None


def set_loader_for_testing(
    loader: Optional[Callable[[str], Optional["TenantContext"]]],
) -> None:
    """Install (or clear with ``None``) a test-only loader.

    The loader receives a ``tenant_id`` and must return either a
    :class:`TenantContext` or ``None`` to signal "unknown tenant".
    """
    global _LOADER_OVERRIDE
    _LOADER_OVERRIDE = loader


def _get_loader_override() -> (
    Optional[Callable[[str], Optional["TenantContext"]]]
):
    return _LOADER_OVERRIDE


__all__ = [
    "DEFAULT_TENANTS_PATH",
    "MissingContextKeyError",
    "TenantConfigError",
    "TenantContext",
    "UnknownTenantError",
    "set_loader_for_testing",
]
