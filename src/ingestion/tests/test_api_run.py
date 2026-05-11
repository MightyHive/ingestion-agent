"""End-to-end tests for ``POST /api/run`` (Phase 3).

Exercises the FastAPI handler against the deterministic ingestion graph
running on the mock connector fixture. No network, no LLM, no real Cloud
Function. We validate the HTTP contract documented in ``docs/api.md``:

* ``200`` on OK/WARN with the ``formatted_response`` body.
* ``400`` on ``request_validator`` ERR.
* ``502`` on ``connector_runner`` ERR.
* Every response carries an ``X-Request-Id`` (uuid) header.
* Deprecated endpoints expose the ``Deprecation`` / ``Sunset`` headers.

The ``main`` module is stubbed before ``api`` is imported because the real
``main`` boots the legacy multi-agent graph (AsyncSqliteSaver, PydanticAI
agents) which is irrelevant here and would slow tests down significantly.
"""

from __future__ import annotations

import sys
import types
import uuid
from pathlib import Path

import pytest

import ingestion.manifest as manifest_pkg
import ingestion.nodes.request_validator as request_validator_module
from ingestion.auth.tenant_context import (
    TenantContext,
    set_loader_for_testing,
)
from ingestion.manifest import Catalog

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_catalog(monkeypatch: pytest.MonkeyPatch) -> Catalog:
    """Point the validator at the fixtures directory instead of the submodule."""
    cat = Catalog(root=FIXTURES_DIR)
    cat.reload()
    monkeypatch.setattr(manifest_pkg, "get_default_catalog", lambda: cat)
    monkeypatch.setattr(
        request_validator_module, "get_default_catalog", lambda: cat
    )
    return cat


@pytest.fixture
def stub_tenant():
    """Stub the tenant resolver so we don't need a real ~/.mds/tenants.json file."""
    set_loader_for_testing(
        lambda tid: TenantContext(
            tenant_id=tid,
            gcp_project="monks-mds-dev",
            service_account="mds-runner@monks-mds-dev.iam.gserviceaccount.com",
            context={"tenant_marker": f"TENANT-{tid.upper()}"},
        )
    )
    try:
        yield
    finally:
        set_loader_for_testing(None)


@pytest.fixture
def api_client(fixture_catalog, stub_tenant, monkeypatch: pytest.MonkeyPatch):
    """Build a FastAPI TestClient with the legacy ``main`` module stubbed.

    The real ``main`` initialises the multi-agent graph + SQLite checkpointer
    on app startup, which is unrelated to ``/api/run`` and slow. We replace
    it in ``sys.modules`` before importing ``api`` so the lifespan hook is a
    no-op and the legacy endpoints raise a clear error if accidentally hit.
    """
    fake_main = types.ModuleType("main")

    async def _noop_init_graph_async() -> None:
        return None

    def _fail_get_compiled_graph():
        raise RuntimeError(
            "legacy multi-agent graph is not initialised in tests; "
            "use POST /api/run instead"
        )

    fake_main.init_graph_async = _noop_init_graph_async
    fake_main.get_compiled_graph = _fail_get_compiled_graph
    monkeypatch.setitem(sys.modules, "main", fake_main)

    # Force a re-import of api so it picks up the stubbed main.
    sys.modules.pop("api", None)
    from fastapi.testclient import TestClient

    import api as api_module  # noqa: WPS433 — local import is intentional

    with TestClient(api_module.app) as client:
        yield client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_request_id(response) -> None:
    """Every response must expose a valid uuid in the X-Request-Id header."""
    request_id = response.headers.get("x-request-id")
    assert request_id, "X-Request-Id header missing"
    # uuid4 raises if the string is malformed.
    uuid.UUID(request_id)


# ---------------------------------------------------------------------------
# 200 — happy path
# ---------------------------------------------------------------------------


def test_run_ok_returns_200_with_formatted_response(api_client) -> None:
    resp = api_client.post(
        "/api/run",
        json={
            "manifest_id": "test_mock_connector",
            "params": {
                "fields": ["id", "label"],
                "simulate_row_count": 2,
            },
        },
    )
    assert resp.status_code == 200, resp.text
    _assert_request_id(resp)

    body = resp.json()
    # Shape of formatted_response (see ingestion/nodes/format_response.py).
    assert body["manifest_id"] == "test_mock_connector"
    assert body["tenant_id"] == "dev"
    assert body["target_table"] == "bronze.test_mock_connector"
    assert body["row_count"] == 2
    assert body["columns"] == ["id", "label"]
    assert isinstance(body["rows_preview"], list)
    assert body["rows_preview"][0]["tenant_seen"] == "TENANT-DEV"
    assert "ddl" in body and "id STRING" in body["ddl"]


# ---------------------------------------------------------------------------
# 200 — WARN path (partial connector response)
# ---------------------------------------------------------------------------


def test_run_warn_partial_still_returns_200(api_client) -> None:
    """Connector with ``status=partial`` is mapped to WARN; the run still
    completes and the API still returns 200 with the formatted_response."""
    resp = api_client.post(
        "/api/run",
        json={
            "manifest_id": "test_mock_connector",
            "params": {
                "fields": [],
                "simulate_status": "partial",
                "simulate_errors": ["rate_limited_partial"],
            },
        },
    )
    assert resp.status_code == 200, resp.text
    _assert_request_id(resp)
    body = resp.json()
    assert body["manifest_id"] == "test_mock_connector"
    # Partial errors surface in the response body for visibility.
    assert "rate_limited_partial" in body.get("errors", [])


# ---------------------------------------------------------------------------
# 400 — validation_failed (request_validator ERR)
# ---------------------------------------------------------------------------


def test_run_missing_required_param_returns_400(api_client) -> None:
    resp = api_client.post(
        "/api/run",
        json={
            "manifest_id": "test_mock_connector",
            "params": {},  # missing required 'fields'
        },
    )
    assert resp.status_code == 400, resp.text
    _assert_request_id(resp)
    body = resp.json()
    assert body["error"] == "validation_failed"
    assert body["node"] == "request_validator"
    assert body["request_id"]


def test_run_unknown_manifest_returns_400(api_client) -> None:
    """An unknown manifest_id is caught by request_validator as a validation
    error, not as a 404; that keeps the contract simple."""
    resp = api_client.post(
        "/api/run",
        json={
            "manifest_id": "nonexistent_manifest",
            "params": {"fields": []},
        },
    )
    assert resp.status_code == 400, resp.text
    _assert_request_id(resp)
    body = resp.json()
    assert body["error"] == "validation_failed"
    assert body["node"] == "request_validator"


# ---------------------------------------------------------------------------
# 502 — connector_failed (connector_runner ERR)
# ---------------------------------------------------------------------------


def test_run_connector_error_returns_502(api_client) -> None:
    resp = api_client.post(
        "/api/run",
        json={
            "manifest_id": "test_mock_connector",
            "params": {
                "fields": [],
                "simulate_status": "error",
                "simulate_errors": ["api_unreachable"],
            },
        },
    )
    assert resp.status_code == 502, resp.text
    _assert_request_id(resp)
    body = resp.json()
    assert body["error"] == "connector_failed"
    assert body["node"] == "connector_runner"
    assert "api_unreachable" in body.get("details", [])


# ---------------------------------------------------------------------------
# Pydantic-level request shape validation
# ---------------------------------------------------------------------------


def test_run_empty_manifest_id_returns_422(api_client) -> None:
    """FastAPI/Pydantic intercepts an empty manifest_id with 422 before we
    even reach the handler. We assert the contract so the frontend knows it."""
    resp = api_client.post(
        "/api/run",
        json={"manifest_id": "", "params": {"fields": []}},
    )
    assert resp.status_code == 422


def test_run_missing_manifest_id_returns_422(api_client) -> None:
    resp = api_client.post("/api/run", json={"params": {"fields": []}})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Deprecated endpoints expose the advisory headers (Phase 4 sunset)
# ---------------------------------------------------------------------------


def test_templates_endpoint_carries_deprecation_headers(api_client) -> None:
    resp = api_client.get("/api/templates")
    assert resp.status_code == 200
    assert resp.headers.get("deprecation") == "true"
    assert resp.headers.get("sunset") == "Phase 4"
    # Link header points at the replacement.
    link = resp.headers.get("link", "")
    assert "/api/catalog" in link and 'rel="successor-version"' in link
