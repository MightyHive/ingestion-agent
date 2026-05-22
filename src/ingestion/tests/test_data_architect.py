"""Unit tests for ``data_architect.to_ddl``.

The DDL generator is deterministic; we assert exact output for a small
manifest, plus the partition / clustering behaviour and error paths.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion.nodes.data_architect import to_ddl

FIXTURE_MANIFEST = (
    Path(__file__).resolve().parent / "fixtures" / "mock_connector" / "manifest.json"
)


def _load_mock() -> dict:
    with FIXTURE_MANIFEST.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def test_to_ddl_basic_shape() -> None:
    manifest = _load_mock()
    ddl, table, columns = to_ddl(manifest, ["id", "label", "value"])
    assert table == "bronze.test_mock_connector"
    assert ddl.startswith("CREATE TABLE IF NOT EXISTS `bronze.test_mock_connector` (")
    assert ddl.endswith(";\n")
    assert "id STRING" in ddl
    assert "value FLOAT64" in ddl
    # No partition declared in the fixture manifest.
    assert "PARTITION BY" not in ddl
    # Clustering is declared in the fixture.
    assert "CLUSTER BY id" in ddl
    assert {c["name"] for c in columns} >= {"id", "label", "value"}


def test_to_ddl_includes_non_selectable_fields() -> None:
    manifest = _load_mock()
    # Force one column to be non-selectable; it must still appear.
    for f in manifest["available_fields"]:
        if f["name"] == "tenant_seen":
            f["selectable"] = False
            break
    ddl, _, columns = to_ddl(manifest, ["id"])
    names = [c["name"] for c in columns]
    assert "tenant_seen" in names, "non-selectable fields must always be included"
    assert "tenant_seen STRING" in ddl


def test_to_ddl_partition_day() -> None:
    manifest = _load_mock()
    manifest["available_fields"].append(
        {"name": "event_date", "type": "DATE", "selectable": False}
    )
    manifest["table_naming"]["partition_field"] = "event_date"
    manifest["table_naming"]["partition_type"] = "DAY"
    ddl, _, _ = to_ddl(manifest, ["id"])
    assert "PARTITION BY event_date" in ddl


def test_to_ddl_partition_month_uses_date_trunc() -> None:
    manifest = _load_mock()
    manifest["available_fields"].append(
        {"name": "event_date", "type": "DATE", "selectable": False}
    )
    manifest["table_naming"]["partition_field"] = "event_date"
    manifest["table_naming"]["partition_type"] = "MONTH"
    ddl, _, _ = to_ddl(manifest, ["id"])
    assert "PARTITION BY DATE_TRUNC(event_date, MONTH)" in ddl


def test_to_ddl_bronze_pattern_tokens() -> None:
    manifest = _load_mock()
    manifest["table_naming"]["bronze_pattern"] = "raw_{platform}.{connector}_v{version_major}"
    _, table, _ = to_ddl(manifest, ["id"])
    assert table == "raw_test.mock_v0"


def test_to_ddl_required_mode_emits_not_null() -> None:
    manifest = _load_mock()
    for f in manifest["available_fields"]:
        if f["name"] == "id":
            f["mode"] = "REQUIRED"
            break
    ddl, _, _ = to_ddl(manifest, ["id"])
    assert "id STRING NOT NULL" in ddl


def test_to_ddl_clustering_max_4() -> None:
    manifest = _load_mock()
    manifest["table_naming"]["clustering_fields"] = [
        "id",
        "label",
        "value",
        "tenant_seen",
        "id",  # 5th — should explode
    ]
    with pytest.raises(ValueError, match="up to 4"):
        to_ddl(manifest, ["id"])


def test_to_ddl_unsupported_type_raises() -> None:
    manifest = _load_mock()
    manifest["available_fields"].append(
        {"name": "weird", "type": "FANTASY_TYPE"}
    )
    with pytest.raises(ValueError, match="unsupported type"):
        to_ddl(manifest, ["weird"])


def test_to_ddl_real_facebook_manifest() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    facebook = repo_root / "connectors-library" / "meta" / "facebook" / "manifest.json"
    if not facebook.exists():
        pytest.skip("connectors-library submodule not initialised")
    with facebook.open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    # Phase 5: the Meta manifest now uses the {tenant_id} token in
    # bronze_pattern, so we need to pass an explicit tenant_id to get a
    # deterministic table name in the test.
    ddl, table, columns = to_ddl(
        manifest,
        ["account_id", "campaign_name", "spend"],
        tenant_id="cliente1",
    )
    assert table == "bronze.meta_facebook_ad_insights_cliente1"
    # Partition + cluster must be honoured.
    assert "PARTITION BY date_start" in ddl
    assert "CLUSTER BY account_id, campaign_id" in ddl
    # date_start / date_stop are non-selectable but must show up.
    names = {c["name"] for c in columns}
    assert "date_start" in names and "date_stop" in names
    # Selected fields must show up.
    assert "spend NUMERIC" in ddl


def test_resolve_table_name_substitutes_tenant_id_token() -> None:
    """The {tenant_id} token must substitute the supplied tenant key.

    This is what gives Phase 5 multi-tenant tables their suffix.
    """
    from ingestion.nodes.data_architect import _resolve_table_name

    manifest = _load_mock()
    manifest["table_naming"]["bronze_pattern"] = "bronze.{id}_{tenant_id}"
    assert (
        _resolve_table_name(manifest, tenant_id="cliente1")
        == "bronze.test_mock_connector_cliente1"
    )


def test_resolve_table_name_sanitises_tenant_id() -> None:
    """tenant_id keys may legitimately contain dashes/uppercase in the
    operator-facing tenants.json, but BigQuery only accepts
    ``[A-Za-z0-9_]`` in identifiers. The substitution must lowercase
    and replace dashes/spaces with underscores to keep the resulting
    table name valid.
    """
    from ingestion.nodes.data_architect import _resolve_table_name

    manifest = _load_mock()
    manifest["table_naming"]["bronze_pattern"] = "bronze.{id}_{tenant_id}"
    assert (
        _resolve_table_name(manifest, tenant_id="Acme-Brand 01")
        == "bronze.test_mock_connector_acme_brand_01"
    )


def test_resolve_table_name_ignores_tenant_id_when_token_absent() -> None:
    """If the manifest's bronze_pattern doesn't reference {tenant_id},
    the parameter is silently ignored. Existing single-tenant manifests
    keep their behaviour unchanged.
    """
    from ingestion.nodes.data_architect import _resolve_table_name

    manifest = _load_mock()
    manifest["table_naming"]["bronze_pattern"] = "bronze.{id}"
    assert (
        _resolve_table_name(manifest, tenant_id="cliente1")
        == "bronze.test_mock_connector"
    )


def test_to_ddl_user_target_table_wins_over_manifest() -> None:
    """``params.target_table`` (via the ``table_target`` arg) must win
    over the manifest substitution. The frontend exposes this so the
    user can override the default destination (e.g. to land in a
    sandbox dataset for a one-off backfill).
    """
    manifest = _load_mock()
    manifest["table_naming"]["bronze_pattern"] = "bronze.{id}_{tenant_id}"
    _ddl, table, _cols = to_ddl(
        manifest,
        ["id"],
        table_target="sandbox.adhoc_run",
        tenant_id="cliente1",
    )
    assert table == "sandbox.adhoc_run"
