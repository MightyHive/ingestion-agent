"""End-to-end tests for ``POST /api/run`` and the catalog endpoints (Phase 4).

Exercises the FastAPI handlers against the deterministic ingestion graph
running on the mock connector fixture. No network, no LLM, no real Cloud
Function. We validate the HTTP contract documented in ``docs/api.md``:

* ``200`` on OK/WARN with the ``formatted_response`` body.
* ``400`` on ``request_validator`` ERR.
* ``502`` on ``connector_runner`` ERR.
* Every response carries an ``X-Request-Id`` (uuid) header.
* The legacy endpoints (``/api/chat``, ``/api/submit_input``,
  ``/api/templates``, ``/api/sessions/{id}/history``) are gone and now
  return ``404`` — the contract the frontend must rely on post-Phase 4.

The lifespan hook that booted the legacy multi-agent graph
(``AsyncSqliteSaver`` + PydanticAI agents) was removed in Phase 4, so this
test no longer needs to stub a fake ``main`` module — ``api`` imports
cleanly with zero side effects.
"""

from __future__ import annotations

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
def api_client(fixture_catalog, stub_tenant):
    """Build a FastAPI TestClient against the Phase 4 ``api`` module.

    Phase 4 removed the lifespan hook, the legacy ``main`` import and all
    multi-agent endpoints, so this fixture is a thin wrapper around
    ``TestClient(api.app)`` — no stubs, no monkeypatching of ``sys.modules``.
    """
    from fastapi.testclient import TestClient

    import api as api_module

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
# 200 — Phase 5 contract: tenant_id in body + target_table override
# ---------------------------------------------------------------------------


def test_run_uses_explicit_tenant_id_from_request_body(api_client) -> None:
    """When the request body carries ``tenant_id``, the resolver must
    receive that value (not the default ``'dev'``). The stub_tenant
    fixture echoes the requested id into ``tenant_marker`` as
    ``TENANT-<UPPER>``, so we can verify the propagation end-to-end
    without touching the real TenantContext loader.

    The mock manifest still uses ``bronze.{id}`` (no {tenant_id}
    token), so the table name is unaffected — that is intentional and
    keeps this test focused on the tenant_id propagation contract.
    """
    resp = api_client.post(
        "/api/run",
        json={
            "manifest_id": "test_mock_connector",
            "tenant_id": "cliente1",
            "params": {"fields": ["id", "label"], "simulate_row_count": 1},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tenant_id"] == "cliente1"
    assert body["rows_preview"][0]["tenant_seen"] == "TENANT-CLIENTE1"


def test_run_blank_tenant_id_falls_back_to_default(api_client) -> None:
    """A blank string from the frontend (empty input field) must be
    treated as 'not provided' — falling back to the default tenant
    — instead of crashing the graph with an unresolvable empty key.
    """
    resp = api_client.post(
        "/api/run",
        json={
            "manifest_id": "test_mock_connector",
            "tenant_id": "   ",  # blanks-only
            "params": {"fields": ["id", "label"], "simulate_row_count": 1},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tenant_id"] == "dev"


def test_run_user_target_table_overrides_manifest_default(api_client) -> None:
    """``params.target_table`` is a Phase 5 system param. The handler
    must accept it (request_validator allows it via
    ``_SYSTEM_PARAM_KEYS``) and ``data_architect`` must use it as the
    destination, ignoring the manifest's ``bronze_pattern``.
    """
    resp = api_client.post(
        "/api/run",
        json={
            "manifest_id": "test_mock_connector",
            "params": {
                "fields": ["id", "label"],
                "simulate_row_count": 1,
                "target_table": "sandbox.adhoc_run",
            },
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["target_table"] == "sandbox.adhoc_run"


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
    even reach the handler. A dedicated RequestValidationError exception
    handler re-emits the 422 with our X-Request-Id header so the trace-id
    contract from docs/api.md §3.3 holds for *every* response, not just
    the ones our handler produced directly."""
    resp = api_client.post(
        "/api/run",
        json={"manifest_id": "", "params": {"fields": []}},
    )
    assert resp.status_code == 422
    _assert_request_id(resp)
    body = resp.json()
    assert "detail" in body
    assert body.get("request_id") == resp.headers.get("x-request-id")


def test_run_missing_manifest_id_returns_422(api_client) -> None:
    resp = api_client.post("/api/run", json={"params": {"fields": []}})
    assert resp.status_code == 422
    _assert_request_id(resp)
    body = resp.json()
    assert body.get("request_id") == resp.headers.get("x-request-id")


# ---------------------------------------------------------------------------
# Removed legacy endpoints — must return 404 post-Phase 4
# ---------------------------------------------------------------------------
#
# In Phase 3 these endpoints existed but carried RFC 8594 deprecation
# headers. In Phase 4 the handlers (and the agent code behind them) were
# deleted entirely. We assert 404 here so a regression that accidentally
# re-introduces a handler is caught by CI.


@pytest.mark.parametrize(
    "method, path, payload",
    [
        ("post", "/api/chat", {"session_id": "abc", "message": "hi"}),
        ("post", "/api/submit_input", {"session_id": "abc", "user_input": "hi"}),
        ("get", "/api/templates", None),
        ("get", "/api/sessions/abc/history", None),
    ],
)
def test_legacy_endpoints_return_404(api_client, method, path, payload) -> None:
    if method == "post":
        resp = api_client.post(path, json=payload)
    else:
        resp = api_client.get(path)
    assert resp.status_code == 404, (
        f"{method.upper()} {path} should be 404 post-Phase 4, got {resp.status_code}"
    )
