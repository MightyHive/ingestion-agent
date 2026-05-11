"""Unit tests for ``request_validator.validate_request``.

These tests do not require LangGraph; they call the pure function with
a hand-built catalog that points at the fixtures directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion.manifest import Catalog
from ingestion.nodes.request_validator import validate_request

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def catalog() -> Catalog:
    cat = Catalog(root=FIXTURES_DIR)
    cat.reload()
    return cat


def test_validate_ok_with_explicit_fields(catalog: Catalog) -> None:
    lol = validate_request(
        manifest_id="test_mock_connector",
        params={"fields": ["id", "label"], "simulate_row_count": 2},
        tenant_id="dev-tenant",
        catalog=catalog,
    )
    assert lol.status == "OK", lol.errors
    assert lol.data["selected_fields"] == ["id", "label"]
    assert lol.data["normalised_params"]["simulate_row_count"] == 2
    # "fields" is required, so it does not have a default; "simulate_status"
    # has default "ok" which should be applied.
    assert lol.data["normalised_params"]["simulate_status"] == "ok"


def test_validate_ok_empty_field_list_expands_to_all_selectable(catalog: Catalog) -> None:
    lol = validate_request(
        manifest_id="test_mock_connector",
        params={"fields": []},
        tenant_id="dev-tenant",
        catalog=catalog,
    )
    assert lol.status == "OK"
    assert set(lol.data["selected_fields"]) == {"id", "label", "value", "tenant_seen"}


def test_validate_err_unknown_manifest(catalog: Catalog) -> None:
    lol = validate_request(
        manifest_id="does_not_exist",
        params={"fields": []},
        tenant_id="dev-tenant",
        catalog=catalog,
    )
    assert lol.status == "ERR"
    assert any("not found in catalog" in line for line in lol.errors + [lol.reason])


def test_validate_err_missing_required_param(catalog: Catalog) -> None:
    lol = validate_request(
        manifest_id="test_mock_connector",
        params={},  # 'fields' is required
        tenant_id="dev-tenant",
        catalog=catalog,
    )
    assert lol.status == "ERR"
    assert any("missing required keys" in e for e in lol.errors)


def test_validate_err_unknown_param(catalog: Catalog) -> None:
    lol = validate_request(
        manifest_id="test_mock_connector",
        params={"fields": [], "totally_unknown": 1},
        tenant_id="dev-tenant",
        catalog=catalog,
    )
    assert lol.status == "ERR"
    assert any("unknown keys" in e for e in lol.errors)


def test_validate_err_field_not_in_available_fields(catalog: Catalog) -> None:
    lol = validate_request(
        manifest_id="test_mock_connector",
        params={"fields": ["id", "nonexistent_field"]},
        tenant_id="dev-tenant",
        catalog=catalog,
    )
    assert lol.status == "ERR"
    assert any("unknown fields" in e for e in lol.errors)


def test_validate_err_minimum_violation(catalog: Catalog) -> None:
    lol = validate_request(
        manifest_id="test_mock_connector",
        params={"fields": [], "simulate_row_count": -5},
        tenant_id="dev-tenant",
        catalog=catalog,
    )
    assert lol.status == "ERR"
    assert any("below minimum" in e for e in lol.errors)


def test_validate_err_enum_violation(catalog: Catalog) -> None:
    lol = validate_request(
        manifest_id="test_mock_connector",
        params={"fields": [], "simulate_status": "huh"},
        tenant_id="dev-tenant",
        catalog=catalog,
    )
    assert lol.status == "ERR"
    assert any("not in enum" in e for e in lol.errors)


def test_validate_err_blank_tenant_id(catalog: Catalog) -> None:
    lol = validate_request(
        manifest_id="test_mock_connector",
        params={"fields": []},
        tenant_id="",
        catalog=catalog,
    )
    assert lol.status == "ERR"


def test_real_facebook_manifest_one_of(tmp_path: Path) -> None:
    """Sanity check that the real Facebook manifest validates a typical request.

    Uses the real submodule's manifest so a regression in one_of /
    field_list parsing surfaces here, without hitting the network.
    """
    repo_root = Path(__file__).resolve().parents[3]
    library = repo_root / "connectors-library"
    if not (library / "meta" / "facebook" / "manifest.json").exists():
        pytest.skip("connectors-library submodule not initialised")
    cat = Catalog(root=library)
    cat.reload()
    lol = validate_request(
        manifest_id="meta_facebook_ad_insights",
        params={
            "fields": ["account_id", "campaign_name", "spend"],
            "days_back": 7,
        },
        tenant_id="dev-tenant",
        catalog=cat,
    )
    assert lol.status == "OK", lol.errors
    assert lol.data["matched_one_of"] == ["days_back"]


def test_one_of_two_groups_provided_is_err(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    library = repo_root / "connectors-library"
    if not (library / "meta" / "facebook" / "manifest.json").exists():
        pytest.skip("connectors-library submodule not initialised")
    cat = Catalog(root=library)
    cat.reload()
    lol = validate_request(
        manifest_id="meta_facebook_ad_insights",
        params={
            "fields": ["account_id"],
            "days_back": 7,
            "date_start": "2026-01-01",
            "date_stop": "2026-01-31",
        },
        tenant_id="dev-tenant",
        catalog=cat,
    )
    assert lol.status == "ERR"
    assert any("groups fully provided" in e for e in lol.errors)
