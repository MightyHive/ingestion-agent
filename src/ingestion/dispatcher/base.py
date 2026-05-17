"""ConnectorDispatcher — runtime selector between LocalBackend and HTTPBackend.

Why an abstraction
------------------
Connectors live in a separate git submodule (``connectors-library``) so
that the same Python module can be:

* Imported and called in-process during local development and tests
  (LocalBackend).
* Deployed as an isolated Cloud Function and invoked over HTTPS in
  production (HTTPBackend).

The dispatcher hides that distinction from the rest of the graph. The
``connector_runner`` node only ever sees :class:`ConnectorResponse`.

The selection key is ``MDS_RUNTIME``. The default is ``local`` so a
freshly-cloned repo runs without surprises.

Phase 2 only ships LocalBackend. HTTPBackend lands in Phase 5.

Connector contract (recap)
--------------------------
Every connector module exposes a ``fetch(params, context) -> dict``
function. The returned dict has the shape::

    {
        "status":  "ok" | "partial" | "error",
        "code":    int,                       # connector-defined sub-code
        "records": dict | list,               # actual data
        "meta":    {... arbitrary ...},
        "errors":  list[str],
    }

This is identical to what a Cloud Function POSTed back via HTTP would
return; LocalBackend simply skips the network hop.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ingestion.auth.tenant_context import TenantContext


@dataclass
class ConnectorResponse:
    """Normalised connector return value.

    Attributes mirror the ``fetch()`` contract. ``records`` is left as a
    free-form value (dict or list) because individual connectors return
    different shapes (e.g. Meta returns ``{'ads': [...], 'campaigns': [...]}``
    while a simpler connector returns a flat list).

    The dispatcher does **not** interpret ``records`` — that is the job
    of ``format_response``.
    """

    status: str
    code: int | str
    records: Any
    meta: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    # Backend-injected diagnostics (timing, backend type) — for the trace.
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls, raw: dict[str, Any], *, diagnostics: dict[str, Any] | None = None
    ) -> "ConnectorResponse":
        """Build a ConnectorResponse from a raw connector return dict."""
        if not isinstance(raw, dict):
            raise BackendError(
                f"connector returned {type(raw).__name__}, expected dict"
            )
        return cls(
            status=str(raw.get("status", "unknown")),
            code=_normalize_connector_code(raw.get("code", 0)),
            records=raw.get("records"),
            meta=dict(raw.get("meta") or {}),
            errors=list(raw.get("errors") or []),
            diagnostics=dict(diagnostics or {}),
        )


class BackendError(Exception):
    """Wrapper for any failure inside a backend (import, network, contract)."""


def _normalize_connector_code(raw: Any) -> int | str:
    """Connectors may return numeric HTTP-style codes or string tokens (e.g. FETCH_OK)."""
    if raw is None:
        return 0
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return 0
        try:
            return int(stripped)
        except ValueError:
            return stripped
    try:
        return int(raw)
    except (TypeError, ValueError):
        return str(raw)


class BackendBase(ABC):
    """Abstract dispatcher backend. Subclassed by LocalBackend / HTTPBackend."""

    name: str = "base"

    @abstractmethod
    def invoke(
        self,
        manifest: dict[str, Any],
        params: dict[str, Any],
        tenant: TenantContext,
    ) -> ConnectorResponse:
        """Run the connector identified by ``manifest`` and return its response.

        Implementations are responsible for:
        - Validating that ``tenant.context`` satisfies
          ``manifest.auth.context_required`` (call
          :meth:`TenantContext.assert_satisfies`).
        - Translating any exception into a :class:`BackendError`.
        - Filling ``ConnectorResponse.diagnostics`` with timing and the
          backend name so the trace can show which path ran.
        """


class ConnectorDispatcher:
    """Frontend to the active backend.

    Parameters
    ----------
    runtime:
        ``"local"`` or ``"http"``. When ``None``, reads ``MDS_RUNTIME``;
        when that is unset, defaults to ``"local"``.
    """

    def __init__(self, runtime: str | None = None) -> None:
        self.runtime = (runtime or os.environ.get("MDS_RUNTIME", "local")).lower()
        self._backend: BackendBase | None = None

    @property
    def backend(self) -> BackendBase:
        """Lazy-construct the backend so import-time failures don't crash startup."""
        if self._backend is None:
            self._backend = self._build_backend(self.runtime)
        return self._backend

    @staticmethod
    def _build_backend(runtime: str) -> BackendBase:
        if runtime == "local":
            from ingestion.dispatcher.local import LocalBackend
            return LocalBackend()
        if runtime == "http":
            raise BackendError(
                "MDS_RUNTIME=http requires HTTPBackend, which lands in Phase 5. "
                "See docs/migration-plan.md."
            )
        raise BackendError(
            f"unknown MDS_RUNTIME '{runtime}'. Allowed: 'local', 'http'."
        )

    def invoke(
        self,
        manifest: dict[str, Any],
        params: dict[str, Any],
        tenant: TenantContext,
    ) -> ConnectorResponse:
        """Delegate to the active backend, with required-key enforcement."""
        required_keys = list(
            (manifest.get("auth") or {}).get("context_required", []) or []
        )
        tenant.assert_satisfies(required_keys)
        return self.backend.invoke(manifest, params, tenant)


__all__ = [
    "BackendBase",
    "BackendError",
    "ConnectorDispatcher",
    "ConnectorResponse",
]
