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

The selection key is ``MDS_RUNTIME``. Allowed values:

* ``local`` (default): always invoke in-process.
* ``http``: always POST to a Cloud Function URL (HTTPBackend).
* ``auto``: per-manifest. If the manifest declares
  ``endpoint.cloud_function_name``, use HTTP; otherwise fall back to
  Local. This is the recommended setting while we migrate connectors
  from Local-only to deployed-CF one at a time during Phase 5.

HTTPBackend landed in Phase 5; see :mod:`ingestion.dispatcher.http`.

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
        ``"local"``, ``"http"``, or ``"auto"``. When ``None``, reads
        ``MDS_RUNTIME``; when that is unset, defaults to ``"local"``.
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
            from ingestion.dispatcher.http import HTTPBackend
            return HTTPBackend()
        if runtime == "auto":
            from ingestion.dispatcher.http import HTTPBackend
            from ingestion.dispatcher.local import LocalBackend
            return AutoBackend(local=LocalBackend(), http=HTTPBackend())
        raise BackendError(
            f"unknown MDS_RUNTIME '{runtime}'. Allowed: 'local', 'http', 'auto'."
        )

    def invoke(
        self,
        manifest: dict[str, Any],
        params: dict[str, Any],
        tenant: TenantContext,
    ) -> ConnectorResponse:
        """Delegate to the active backend.

        Note on ``auth.context_required`` enforcement
        --------------------------------------------
        Prior to Phase 5 the dispatcher itself called
        ``tenant.assert_satisfies(required_keys)`` here. That made sense
        while every connector ran in-process via :class:`LocalBackend`
        and read its credentials out of ``tenant.context``. With
        :class:`HTTPBackend` the CF resolves its own secrets from Secret
        Manager using its own SA identity, so the MDS backend has no
        reason to populate (or even know about) ``access_token`` /
        ``ad_account_id`` for the tenant. Enforcing
        ``context_required`` here would force operators to put dummy
        placeholders in ``tenants.json`` just to silence the check.

        The validation now lives inside :class:`LocalBackend.invoke`
        (where it can fail fast before importing the connector module),
        while :class:`HTTPBackend.invoke` skips it entirely. AutoBackend
        is unaffected because it just delegates.
        """
        return self.backend.invoke(manifest, params, tenant)


class AutoBackend(BackendBase):
    """Routes per-manifest between Local and HTTP backends.

    Selection rule (intentionally simple — we want it grep-able):

    * If ``manifest.endpoint.cloud_function_name`` is present → HTTP.
    * Otherwise → Local.

    Rationale: the presence of a ``cloud_function_name`` in the manifest
    is the explicit signal that this connector has been deployed and
    should be invoked over the wire. Connectors still on the
    Local-only path simply don't declare that field. This keeps the
    Phase 5 migration incremental: we flip connectors one at a time by
    adding the field to the manifest, with no env changes per
    deployment.
    """

    name = "auto"

    def __init__(self, *, local: BackendBase, http: BackendBase) -> None:
        self._local = local
        self._http = http

    def invoke(
        self,
        manifest: dict[str, Any],
        params: dict[str, Any],
        tenant: TenantContext,
    ) -> ConnectorResponse:
        endpoint = manifest.get("endpoint") or {}
        if endpoint.get("cloud_function_name"):
            return self._http.invoke(manifest, params, tenant)
        return self._local.invoke(manifest, params, tenant)


__all__ = [
    "BackendBase",
    "BackendError",
    "ConnectorDispatcher",
    "ConnectorResponse",
]
