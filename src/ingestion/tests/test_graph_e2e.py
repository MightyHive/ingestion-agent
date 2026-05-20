"""End-to-end test for the deterministic ingestion graph.

Wires the full pipeline against the mock connector fixture:

* request_validator     →
* data_architect        →
* connector_runner      →
* format_response       → END

No network. No LLM. No real Cloud Function.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import ingestion.manifest as manifest_pkg
import ingestion.nodes.request_validator as request_validator_module
from ingestion.graph import build_graph
from ingestion.manifest import Catalog

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


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


def _resolved_tenant(tenant_id: str = "dev") -> dict:
    return {
        "tenant_id": tenant_id,
        "gcp_project": "monks-mds-dev",
        "service_account": "mds-runner@monks-mds-dev.iam.gserviceaccount.com",
        "context": {"tenant_marker": f"TENANT-{tenant_id.upper()}"},
    }


def test_graph_happy_path(fixture_catalog) -> None:
    graph = build_graph()
    final = graph.invoke(
        {
            "manifest_id": "test_mock_connector",
            "params": {"fields": ["id", "label"], "simulate_row_count": 2},
            "tenant_id": "dev",
            "connection_id": "conn-1",
            "resolved_tenant": _resolved_tenant("dev"),
            "node_results": [],
            "obs_usages": [],
        }
    )

    assert final["last_status"] == "OK"
    assert final.get("final_error") is None
    assert final["target_table"] == "bronze.test_mock_connector"
    assert "id STRING" in final["ddl"]

    formatted = final["formatted_response"]
    assert formatted["row_count"] == 2
    assert formatted["columns"] == ["id", "label"]
    assert formatted["rows_preview"][0]["tenant_seen"] == "TENANT-DEV"

    # Trace order: validator, architect, runner, formatter
    statuses = [r["node"] for r in final["node_results"]]
    assert statuses == [
        "request_validator",
        "data_architect",
        "connector_runner",
        "format_response",
    ]


def test_graph_short_circuits_on_validation_err(fixture_catalog) -> None:
    graph = build_graph()
    final = graph.invoke(
        {
            "manifest_id": "test_mock_connector",
            "params": {},  # missing required 'fields'
            "tenant_id": "dev",
            "connection_id": "conn-1",
            "resolved_tenant": _resolved_tenant("dev"),
            "node_results": [],
            "obs_usages": [],
        }
    )
    assert final["last_status"] == "ERR"
    assert final.get("final_error")
    # Only the validator ran.
    nodes_executed = [r["node"] for r in final["node_results"]]
    assert nodes_executed == ["request_validator"]


def test_graph_propagates_connector_error(fixture_catalog) -> None:
    graph = build_graph()
    final = graph.invoke(
        {
            "manifest_id": "test_mock_connector",
            "params": {
                "fields": [],
                "simulate_status": "error",
                "simulate_errors": ["api_unreachable"],
            },
            "tenant_id": "dev",
            "connection_id": "conn-1",
            "resolved_tenant": _resolved_tenant("dev"),
            "node_results": [],
            "obs_usages": [],
        }
    )
    assert final["last_status"] == "ERR"
    nodes_executed = [r["node"] for r in final["node_results"]]
    # Validator + architect succeed, runner errors out.
    assert nodes_executed == [
        "request_validator",
        "data_architect",
        "connector_runner",
    ]
    runner_lol = final["node_results"][-1]
    assert runner_lol["status"] == "ERR"
    assert "api_unreachable" in runner_lol["errors"]


def test_graph_warn_on_partial(fixture_catalog) -> None:
    graph = build_graph()
    final = graph.invoke(
        {
            "manifest_id": "test_mock_connector",
            "params": {
                "fields": [],
                "simulate_status": "partial",
                "simulate_errors": ["rate_limited_partial"],
            },
            "tenant_id": "dev",
            "connection_id": "conn-1",
            "resolved_tenant": _resolved_tenant("dev"),
            "node_results": [],
            "obs_usages": [],
        }
    )
    # Partial → run completes, but runner LOL is WARN.
    runner_lol = next(
        r for r in final["node_results"] if r["node"] == "connector_runner"
    )
    assert runner_lol["status"] == "WARN"
    assert final.get("formatted_response") is not None
