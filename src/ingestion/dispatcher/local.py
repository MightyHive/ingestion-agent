"""LocalBackend — invokes connector modules in-process via importlib.

Used for:

* Local development (no Cloud Functions deployed yet).
* CI tests against fixture connectors checked into
  ``src/ingestion/tests/fixtures/``.
* Reproducing production bugs locally with a mock tenant context.

Module path resolution
----------------------
The connectors-library submodule is added to ``sys.path`` (idempotently)
on first invocation, plus any extra search paths provided via the
``MDS_LOCAL_BACKEND_PATHS`` env var (colon-separated, mirroring
``PYTHONPATH``). Tests use the env var to register a fixture directory
without polluting the real submodule.

Failure mapping
---------------
Every internal exception is wrapped in :class:`BackendError` so callers
only need to catch one exception type. Notable cases:

* ``ModuleNotFoundError`` → "module_path '<x>' not importable"
* ``AttributeError`` for missing function → "function_name '<x>' not found"
* Any other exception from the connector → wrapped with the original
  message and traceback preserved via ``__cause__``.
"""

from __future__ import annotations

import importlib
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable

from ingestion.auth.tenant_context import TenantContext
from ingestion.dispatcher.base import (
    BackendBase,
    BackendError,
    ConnectorResponse,
)

# Repo root: src/ingestion/dispatcher/local.py → parents[3]
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LIBRARY_ROOT = _REPO_ROOT / "connectors-library"

_PATHS_ADDED: set[str] = set()


def _ensure_path(p: Path) -> None:
    """Idempotently prepend ``p`` to ``sys.path`` if it exists."""
    if not p.exists():
        return
    s = str(p.resolve())
    if s in _PATHS_ADDED:
        return
    if s not in sys.path:
        sys.path.insert(0, s)
    _PATHS_ADDED.add(s)


def _seed_sys_path() -> None:
    """Add the connectors-library and any MDS_LOCAL_BACKEND_PATHS entries.

    Called lazily from :meth:`LocalBackend.invoke` so a missing submodule
    doesn't crash app startup.
    """
    _ensure_path(DEFAULT_LIBRARY_ROOT)
    extra = os.environ.get("MDS_LOCAL_BACKEND_PATHS", "")
    for entry in extra.split(":"):
        if entry.strip():
            _ensure_path(Path(entry.strip()).expanduser())


class LocalBackend(BackendBase):
    """Imports and calls the connector module described by the manifest.

    Threading: ``importlib.import_module`` caches modules in ``sys.modules``
    so successive invocations are cheap. The backend itself holds no
    state besides the cache, so a single instance is fine for the
    process lifetime.
    """

    name = "local"

    def invoke(
        self,
        manifest: dict[str, Any],
        params: dict[str, Any],
        tenant: TenantContext,
    ) -> ConnectorResponse:
        endpoint = manifest.get("endpoint") or {}
        module_path = endpoint.get("module_path")
        function_name = endpoint.get("function_name", "fetch")
        if not module_path:
            raise BackendError(
                f"manifest '{manifest.get('id')}' has no endpoint.module_path"
            )

        _seed_sys_path()

        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as exc:
            raise BackendError(
                f"module_path '{module_path}' not importable: {exc}. "
                f"Check that connectors-library is initialized "
                f"(git submodule update --init) and that "
                f"MDS_LOCAL_BACKEND_PATHS covers fixture directories if any."
            ) from exc

        fn = getattr(module, function_name, None)
        if fn is None or not callable(fn):
            raise BackendError(
                f"module '{module_path}' has no callable '{function_name}'"
            )

        diagnostics: dict[str, Any] = {
            "backend": self.name,
            "module_path": module_path,
            "function_name": function_name,
            "tenant_id": tenant.tenant_id,
        }
        started = time.monotonic()
        try:
            raw = _call_fetch(fn, params, dict(tenant.context))
        except BackendError:
            raise
        except Exception as exc:  # noqa: BLE001 — we want a single trap point
            diagnostics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
            raise BackendError(
                f"connector '{module_path}.{function_name}' raised "
                f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            ) from exc
        diagnostics["elapsed_ms"] = int((time.monotonic() - started) * 1000)

        return ConnectorResponse.from_dict(raw, diagnostics=diagnostics)


def _call_fetch(
    fn: Callable[..., Any], params: dict[str, Any], context: dict[str, Any]
) -> Any:
    """Invoke ``fetch`` with the canonical ``(params, context)`` signature.

    Some legacy connectors use a single positional ``params`` plus
    ``**kwargs`` for context; we try the canonical form first and fall
    back to keyword expansion only on TypeError.
    """
    try:
        return fn(params, context)
    except TypeError:
        return fn(params, **context)


__all__ = ["DEFAULT_LIBRARY_ROOT", "LocalBackend"]
