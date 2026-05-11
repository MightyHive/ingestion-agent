"""Unit tests for ``LocalBackend`` and ``ConnectorDispatcher``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion.auth.tenant_context import (
    MissingContextKeyError,
    TenantContext,
)
from ingestion.dispatcher.base import (
    BackendError,
    ConnectorDispatcher,
    ConnectorResponse,
)
from ingestion.dispatcher.local import LocalBackend

FIXTURE_MANIFEST = (
    Path(__file__).resolve().parent / "fixtures" / "mock_connector" / "manifest.json"
)


def _load_manifest() -> dict:
    with FIXTURE_MANIFEST.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _tenant() -> TenantContext:
    return TenantContext(
        tenant_id="dev",
        gcp_project="p",
        service_account="s",
        context={"tenant_marker": "DEV-MARK"},
    )


def test_local_backend_invokes_mock_connector() -> None:
    backend = LocalBackend()
    resp = backend.invoke(_load_manifest(), {"fields": [], "simulate_row_count": 4}, _tenant())
    assert isinstance(resp, ConnectorResponse)
    assert resp.status == "ok"
    assert resp.code == 200
    assert isinstance(resp.records, list)
    assert len(resp.records) == 4
    assert resp.records[0]["tenant_seen"] == "DEV-MARK"
    assert resp.diagnostics["backend"] == "local"
    assert "elapsed_ms" in resp.diagnostics


def test_local_backend_module_not_found() -> None:
    backend = LocalBackend()
    manifest = _load_manifest()
    manifest["endpoint"]["module_path"] = "definitely.not.a.module"
    with pytest.raises(BackendError, match="not importable"):
        backend.invoke(manifest, {"fields": []}, _tenant())


def test_local_backend_function_not_found() -> None:
    backend = LocalBackend()
    manifest = _load_manifest()
    manifest["endpoint"]["function_name"] = "nope"
    with pytest.raises(BackendError, match="no callable"):
        backend.invoke(manifest, {"fields": []}, _tenant())


def test_dispatcher_enforces_required_context_keys() -> None:
    disp = ConnectorDispatcher(runtime="local")
    manifest = _load_manifest()
    bare_tenant = TenantContext(
        tenant_id="dev", gcp_project="p", service_account="s", context={}
    )
    with pytest.raises(MissingContextKeyError):
        disp.invoke(manifest, {"fields": []}, bare_tenant)


def test_dispatcher_unknown_runtime() -> None:
    with pytest.raises(BackendError, match="unknown MDS_RUNTIME"):
        ConnectorDispatcher(runtime="zarko").backend  # accessing builds it


def test_dispatcher_http_runtime_phase5_message() -> None:
    with pytest.raises(BackendError, match="Phase 5"):
        ConnectorDispatcher(runtime="http").backend
