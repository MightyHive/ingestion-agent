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

import json
import uuid
from pathlib import Path

import pytest

import ingestion.manifest as manifest_pkg
import ingestion.nodes.request_validator as request_validator_module
from ingestion.auth.tenant_context import TenantContext
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


def _fake_tenant_context(tenant_id: str) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id,
        gcp_project="monks-mds-dev",
        service_account="mds-runner@monks-mds-dev.iam.gserviceaccount.com",
        context={"tenant_marker": f"TENANT-{tenant_id.upper()}"},
    )


@pytest.fixture
def api_client(fixture_catalog, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Build a FastAPI TestClient against the Phase 4 ``api`` module.

    Phase 4 removed the lifespan hook, the legacy ``main`` import and all
    multi-agent endpoints, so this fixture is a thin wrapper around
    ``TestClient(api.app)`` — no stubs, no monkeypatching of ``sys.modules``.
    """
    from fastapi.testclient import TestClient

    registry_file = tmp_path / "user_tenants.json"
    registry_file.write_text(
        json.dumps(
            {
                "users": {"alice": ["dev"], "bob": ["tenant-b"]},
                "api_keys": {"key-alice": "alice"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MDS_USER_TENANTS_FILE", str(registry_file))
    monkeypatch.delenv("MDS_AUTH_DISABLED", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import api as api_module

    monkeypatch.setattr(api_module, "get_default_catalog", lambda: fixture_catalog)
    monkeypatch.setattr(
        api_module,
        "resolve_for_run",
        lambda tenant_id, connection_id, expected_platform: _fake_tenant_context(
            tenant_id
        ),
    )

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


def _run_headers(tenant_id: str = "dev") -> dict[str, str]:
    return {"X-Tenant-Id": tenant_id, "X-User-Id": "alice"}


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
            "connection_id": "conn-1",
        },
        headers=_run_headers(),
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
            "connection_id": "conn-1",
        },
        headers=_run_headers(),
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
            "connection_id": "conn-1",
        },
        headers=_run_headers(),
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
            "connection_id": "conn-1",
        },
        headers=_run_headers(),
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
            "connection_id": "conn-1",
        },
        headers=_run_headers(),
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
        json={"manifest_id": "", "params": {"fields": []}, "connection_id": "conn-1"},
        headers=_run_headers(),
    )
    assert resp.status_code == 422
    _assert_request_id(resp)
    body = resp.json()
    assert "detail" in body
    assert body.get("request_id") == resp.headers.get("x-request-id")


def test_run_missing_manifest_id_returns_422(api_client) -> None:
    resp = api_client.post(
        "/api/run",
        json={"params": {"fields": []}, "connection_id": "conn-1"},
        headers=_run_headers(),
    )
    assert resp.status_code == 422
    _assert_request_id(resp)
    body = resp.json()
    assert body.get("request_id") == resp.headers.get("x-request-id")


def test_run_missing_connection_id_returns_422(api_client) -> None:
    resp = api_client.post(
        "/api/run",
        json={"manifest_id": "test_mock_connector", "params": {"fields": []}},
        headers=_run_headers(),
    )
    assert resp.status_code == 422
    _assert_request_id(resp)


def test_run_missing_tenant_header_returns_400(api_client) -> None:
    resp = api_client.post(
        "/api/run",
        json={
            "manifest_id": "test_mock_connector",
            "params": {"fields": []},
            "connection_id": "conn-1",
        },
    )
    assert resp.status_code == 400
    _assert_request_id(resp)
    assert resp.json()["error"] == "missing_tenant_header"


def test_run_missing_user_header_returns_401(api_client) -> None:
    resp = api_client.post(
        "/api/run",
        json={
            "manifest_id": "test_mock_connector",
            "params": {"fields": []},
            "connection_id": "conn-1",
        },
        headers={"X-Tenant-Id": "dev"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "missing_user"


def test_run_tenant_forbidden_returns_403(api_client) -> None:
    resp = api_client.post(
        "/api/run",
        json={
            "manifest_id": "test_mock_connector",
            "params": {"fields": []},
            "connection_id": "conn-1",
        },
        headers={"X-Tenant-Id": "tenant-b", "X-User-Id": "alice"},
    )
    assert resp.status_code == 403
    assert resp.json()["error"] == "tenant_forbidden"


def test_run_inactive_connection_returns_409(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    import api as api_module

    def _raise(*args, **kwargs):
        raise api_module.ConnectionInactiveError("connection 'conn-1' is not active")

    monkeypatch.setattr(api_module, "resolve_for_run", _raise)

    resp = api_client.post(
        "/api/run",
        json={
            "manifest_id": "test_mock_connector",
            "params": {"fields": []},
            "connection_id": "conn-1",
        },
        headers=_run_headers(),
    )
    assert resp.status_code == 409
    _assert_request_id(resp)
    assert resp.json()["error"] == "connection_inactive"


def test_run_provider_mismatch_returns_400(api_client, monkeypatch: pytest.MonkeyPatch) -> None:
    import api as api_module

    def _raise(*args, **kwargs):
        raise api_module.ConnectionProviderMismatchError("provider mismatch")

    monkeypatch.setattr(api_module, "resolve_for_run", _raise)

    resp = api_client.post(
        "/api/run",
        json={
            "manifest_id": "test_mock_connector",
            "params": {"fields": []},
            "connection_id": "conn-1",
        },
        headers=_run_headers(),
    )
    assert resp.status_code == 400
    _assert_request_id(resp)
    assert resp.json()["error"] == "provider_mismatch"


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
