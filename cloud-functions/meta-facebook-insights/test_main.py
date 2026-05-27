"""Unit tests for meta-facebook-insights Cloud Function (``main.py``).

The tests are fully hermetic: they do NOT require the
``functions-framework`` package, the ``google-cloud-*`` SDKs, or any
network access. ``conftest.py`` stubs everything before ``main`` is
imported, and each test monkeypatches ``_resolve_secret`` /
``_write_records_to_bq`` / ``facebook_ads.fetch`` to inject deterministic
behaviour.

Coverage map
============

* Validation guards: missing tenant_id, missing manifest_id, wrong
  manifest_id, malformed params.
* Secret resolution: happy path, missing secret -> MISSING_SECRET.
* Connector errors: each known error code surfaces with the right
  HTTP status (Meta-specific codes).
* Connector raises: unexpected exception wrapped in CONNECTOR_RAISED.
* Multi-level records dict: response_subkey picks the right level for
  BQ + preview; total_campaigns/total_adsets/total_ads in meta.
* BQ write: happy path with stub, target_table normalisation, invalid table.
* Records preview cap (applied to the SELECTED level, not the whole dict).
* Schema derivation: known columns come from manifest (FLOAT64/NUMERIC/DATE/JSON),
  unknown columns fall back to STRING.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

# --- Test fixtures: import main and inject a stub connector ---------------

# Ensure the CF dir is on sys.path so ``import main`` works from any cwd.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def _install_stub_connector(monkeypatch, return_value=None, raises=None):
    """Plant a fake ``facebook_ads`` module into ``sys.modules``.

    ``main`` does ``from facebook_ads import fetch`` lazily inside
    ``run()``, so we need the module to exist by then. Returns the
    underlying recorder so tests can assert on the call.
    """
    recorder = {"call_count": 0, "params": None, "context": None}

    def _fake_fetch(params, context):
        recorder["call_count"] += 1
        recorder["params"] = params
        recorder["context"] = context
        if raises is not None:
            raise raises
        return return_value or {
            "status": "OK",
            "code": "FETCH_OK",
            "records": {"campaigns": [], "adsets": [], "ads": []},
            "meta": {},
            "errors": [],
        }

    stub_mod = types.ModuleType("facebook_ads")
    stub_mod.fetch = _fake_fetch
    monkeypatch.setitem(sys.modules, "facebook_ads", stub_mod)
    return recorder


class _FakeRequest:
    """Minimal stand-in for a flask.Request-like object as passed by
    functions-framework. ``main.run()`` only ever calls ``get_json``."""

    def __init__(self, body):
        self._body = body

    def get_json(self, silent=False):
        return self._body


def _base_body(**overrides):
    body = {
        "tenant_id": "cliente1",
        "manifest_id": "meta_facebook_ad_insights",
        "manifest_version": "0.1.0",
        "connection_id": "test-conn-1",
        "params": {"date_preset": "last_7d"},
    }
    body.update(overrides)
    return body


# --- Import main AFTER conftest has installed the stubs -------------------

import main as cf_main  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_manifest_cache():
    """Force main to re-read manifest.json each test so test ordering is irrelevant."""
    cf_main._MANIFEST_CACHE = None
    yield
    cf_main._MANIFEST_CACHE = None


@pytest.fixture
def gcp_project_env(monkeypatch):
    monkeypatch.setenv("GCP_PROJECT", "monks-mds-dev-test")
    return "monks-mds-dev-test"


@pytest.fixture
def good_secrets(monkeypatch):
    """Pretend SM returns the new unified JSON secret for cliente1/test-conn-1."""

    def _fake_resolve(secret_id, version="latest"):
        # New format: single JSON secret named {tenant}-meta-{connection_id}
        if secret_id == "cliente1-meta-test-conn-1":
            return '{"access_token":"EAA-fake-token-1234567890","ad_account_id":"act_1234567890"}'
        # Legacy fallback (two plain-string secrets)
        if secret_id.endswith("_access_token"):
            return "EAA-fake-token-1234567890"
        if secret_id.endswith("_ad_account_id"):
            return "act_1234567890"
        raise RuntimeError(f"unexpected secret_id={secret_id}")

    monkeypatch.setattr(cf_main, "_resolve_secret", _fake_resolve)


# =========================================================================
# Validation guards
# =========================================================================


def test_run_rejects_missing_tenant_id(gcp_project_env, monkeypatch):
    _install_stub_connector(monkeypatch)
    body, status = cf_main.run(_FakeRequest(_base_body(tenant_id=None)))
    assert status == 400
    assert body["code"] == "MISSING_TENANT_ID"


def test_run_rejects_missing_manifest_id(gcp_project_env, monkeypatch):
    _install_stub_connector(monkeypatch)
    body, status = cf_main.run(_FakeRequest(_base_body(manifest_id=None)))
    assert status == 400
    assert body["code"] == "MISSING_MANIFEST_ID"


def test_run_rejects_wrong_manifest_id(gcp_project_env, monkeypatch):
    _install_stub_connector(monkeypatch)
    body, status = cf_main.run(_FakeRequest(_base_body(manifest_id="dv360_reports")))
    assert status == 400
    assert body["code"] == "MANIFEST_MISMATCH"
    assert "meta_facebook_ad_insights" in body["errors"][0]


def test_run_rejects_non_dict_params(gcp_project_env, monkeypatch):
    _install_stub_connector(monkeypatch)
    body, status = cf_main.run(_FakeRequest(_base_body(params="not-a-dict")))
    assert status == 400
    assert body["code"] == "INVALID_PARAMS"


# =========================================================================
# Secret resolution
# =========================================================================


def test_run_returns_missing_secret_when_sm_fails(gcp_project_env, monkeypatch):
    _install_stub_connector(monkeypatch)

    def _fake_resolve(secret_id, version="latest"):
        raise PermissionError(f"403 on {secret_id}")

    monkeypatch.setattr(cf_main, "_resolve_secret", _fake_resolve)
    body, status = cf_main.run(_FakeRequest(_base_body()))
    assert status == 500
    assert body["code"] == "MISSING_SECRET"
    assert "cliente1-meta-test-conn-1" in body["errors"][0]


def test_build_connector_context_returns_access_token_and_account(gcp_project_env, good_secrets):
    ctx = cf_main._build_connector_context("cliente1", connection_id="test-conn-1")
    assert ctx["access_token"] == "EAA-fake-token-1234567890"
    assert ctx["ad_account_id"] == "act_1234567890"


def test_secrets_named_by_tenant_id(gcp_project_env, monkeypatch):
    """connection_id 'test-conn-1' + tenant 'cliente1' -> 'cliente1-meta-test-conn-1'."""
    seen = []

    def _fake_resolve(secret_id, version="latest"):
        seen.append(secret_id)
        return '{"access_token":"x","ad_account_id":"act_y"}'

    monkeypatch.setattr(cf_main, "_resolve_secret", _fake_resolve)
    cf_main._build_connector_context("cliente1", connection_id="test-conn-1")
    assert seen == ["cliente1-meta-test-conn-1"]


def test_build_connector_context_legacy_fallback(gcp_project_env, monkeypatch):
    """Without connection_id, falls back to two separate plain-string secrets."""
    seen = []

    def _fake_resolve(secret_id, version="latest"):
        seen.append(secret_id)
        return "x" if secret_id.endswith("_access_token") else "act_y"

    monkeypatch.setattr(cf_main, "_resolve_secret", _fake_resolve)
    ctx = cf_main._build_connector_context("cliente1")
    assert seen == [
        "client_cliente1_meta_access_token",
        "client_cliente1_meta_ad_account_id",
    ]
    assert ctx["access_token"] == "x"
    assert ctx["ad_account_id"] == "act_y"


# =========================================================================
# Connector outcome routing (Meta-specific error codes)
# =========================================================================


@pytest.mark.parametrize(
    "connector_code, expected_status",
    [
        ("UNAUTHORIZED", 401),
        ("MISSING_CREDENTIALS", 401),
        ("FORBIDDEN", 403),
        ("MISSING_ACCOUNT_ID", 400),
        ("INVALID_PARAMS", 400),
        ("UNEXPECTED_ERROR", 500),
    ],
)
def test_run_maps_connector_error_codes_to_http_status(
    gcp_project_env, good_secrets, monkeypatch, connector_code, expected_status
):
    _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "ERR",
            "code": connector_code,
            "records": {"campaigns": [], "adsets": [], "ads": []},
            "meta": {},
            "errors": ["bork"],
        },
    )
    body, status = cf_main.run(_FakeRequest(_base_body()))
    assert status == expected_status
    assert body["code"] == connector_code
    assert body["status"] == "ERR"
    # Even on error, records must be echoed as a list (selected level), not a dict.
    assert isinstance(body["records"], list)


def test_run_wraps_connector_exception_as_connector_raised(
    gcp_project_env, good_secrets, monkeypatch
):
    _install_stub_connector(monkeypatch, raises=ValueError("boom"))
    body, status = cf_main.run(_FakeRequest(_base_body()))
    assert status == 500
    assert body["code"] == "CONNECTOR_RAISED"
    assert "ValueError" in body["errors"][0]


def test_run_returns_connector_not_packaged_if_import_fails(
    gcp_project_env, good_secrets, monkeypatch
):
    # Force the lazy import inside run() to fail.
    monkeypatch.delitem(sys.modules, "facebook_ads", raising=False)

    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def _failing_import(name, *args, **kwargs):
        if name == "facebook_ads":
            raise ImportError("no module")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _failing_import)
    body, status = cf_main.run(_FakeRequest(_base_body()))
    assert status == 500
    assert body["code"] == "CONNECTOR_NOT_PACKAGED"


# =========================================================================
# Multi-level records dict + response_subkey selection
# =========================================================================


def test_run_writes_only_selected_subkey_level_to_bq(
    gcp_project_env, good_secrets, monkeypatch
):
    """Connector returns {campaigns, adsets, ads}; BQ must receive ONLY 'ads'."""
    records_dict = {
        "campaigns": [{"campaign_id": "c1"}],
        "adsets": [{"adset_id": "a1"}, {"adset_id": "a2"}],
        "ads": [
            {"ad_id": "x1", "impressions": 10},
            {"ad_id": "x2", "impressions": 20},
            {"ad_id": "x3", "impressions": 30},
        ],
    }
    _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "OK", "code": "FETCH_OK",
            "records": records_dict, "meta": {}, "errors": [],
        },
    )

    seen = {}

    def _fake_bq(*, table_id, records):
        seen["table_id"] = table_id
        seen["row_count"] = len(records)
        seen["sample_ad_id"] = records[0].get("ad_id") if records else None
        return {"bq_table_id": table_id, "rows_written": len(records), "schema_created": True}

    monkeypatch.setattr(cf_main, "_write_records_to_bq", _fake_bq)

    body, status = cf_main.run(_FakeRequest(_base_body(target_table="bronze.meta_facebook_ad_insights")))
    assert status == 200
    # Only the "ads" level was written.
    assert seen["row_count"] == 3
    assert seen["sample_ad_id"] == "x1"
    # Response echoes the selected level as a list.
    assert isinstance(body["records"], list)
    assert len(body["records"]) == 3
    # Meta surfaces total counts of all three levels.
    assert body["meta"]["total_campaigns"] == 1
    assert body["meta"]["total_adsets"] == 2
    assert body["meta"]["total_ads"] == 3
    assert body["meta"]["response_subkey"] == "ads"


def test_select_level_records_missing_subkey_returns_empty():
    out = cf_main._select_level_records({"campaigns": [{"x": 1}]}, "ads")
    assert out == []


def test_select_level_records_not_a_dict_returns_empty():
    assert cf_main._select_level_records(None, "ads") == []
    assert cf_main._select_level_records([{"ad_id": "x"}], "ads") == []
    assert cf_main._select_level_records("not-a-dict", "ads") == []


def test_select_level_records_returns_list_when_present():
    out = cf_main._select_level_records({"ads": [{"ad_id": "x"}]}, "ads")
    assert out == [{"ad_id": "x"}]


# =========================================================================
# Successful round-trip without BQ write
# =========================================================================


def test_run_happy_path_no_target_table(gcp_project_env, good_secrets, monkeypatch):
    records_dict = {
        "campaigns": [],
        "adsets": [],
        "ads": [{"ad_id": "x1", "impressions": 10, "date_start": "2026-05-13"}],
    }
    recorder = _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "OK", "code": "FETCH_OK",
            "records": records_dict,
            "meta": {"account": "act_1234567890"}, "errors": [],
        },
    )
    # Confirm BQ writer is NOT called when target_table is absent.
    monkeypatch.setattr(
        cf_main,
        "_write_records_to_bq",
        lambda **_: (_ for _ in ()).throw(AssertionError("BQ writer must not run")),
    )

    body, status = cf_main.run(_FakeRequest(_base_body()))
    assert status == 200
    assert body["status"] == "OK"
    assert body["code"] == "FETCH_OK"
    assert body["records"] == records_dict["ads"]
    assert body["meta"]["tenant_id"] == "cliente1"
    assert recorder["call_count"] == 1
    # The connector must have received a sane context.
    assert recorder["context"]["access_token"] == "EAA-fake-token-1234567890"
    assert recorder["context"]["ad_account_id"] == "act_1234567890"


def test_fields_lifted_to_params_for_connector(gcp_project_env, good_secrets, monkeypatch):
    recorder = _install_stub_connector(monkeypatch)
    body = _base_body(fields=["ad_id", "impressions", "spend"])
    cf_main.run(_FakeRequest(body))
    # HTTPBackend lifted ``fields`` to top-level; CF re-injects into params.
    assert recorder["params"]["fields"] == ["ad_id", "impressions", "spend"]


# =========================================================================
# BigQuery write
# =========================================================================


def test_run_writes_to_bq_when_target_table_present(
    gcp_project_env, good_secrets, monkeypatch
):
    records_dict = {
        "campaigns": [],
        "adsets": [],
        "ads": [{"ad_id": "x1", "impressions": 10, "spend": "1.50"}],
    }
    _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "OK", "code": "FETCH_OK", "records": records_dict,
            "meta": {"account": "act_1234567890"}, "errors": [],
        },
    )

    seen = {}

    def _fake_bq(*, table_id, records):
        seen["table_id"] = table_id
        seen["row_count"] = len(records)
        return {"bq_table_id": table_id, "rows_written": len(records), "schema_created": True}

    monkeypatch.setattr(cf_main, "_write_records_to_bq", _fake_bq)

    body, status = cf_main.run(_FakeRequest(_base_body(target_table="bronze.meta_facebook_ad_insights")))
    assert status == 200
    assert body["status"] == "OK"
    assert seen["table_id"] == "monks-mds-dev-test.bronze.meta_facebook_ad_insights"
    assert seen["row_count"] == 1
    assert body["meta"]["bq_table_id"] == "monks-mds-dev-test.bronze.meta_facebook_ad_insights"
    assert body["meta"]["rows_written"] == 1
    assert body["meta"]["schema_created"] is True


def test_bq_write_failure_returns_bq_write_failed(
    gcp_project_env, good_secrets, monkeypatch
):
    _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "OK", "code": "FETCH_OK",
            "records": {"campaigns": [], "adsets": [], "ads": [{"ad_id": "x"}]},
            "meta": {}, "errors": [],
        },
    )

    def _explode(**_):
        raise RuntimeError("BQ exploded")

    monkeypatch.setattr(cf_main, "_write_records_to_bq", _explode)

    body, status = cf_main.run(_FakeRequest(_base_body(target_table="bronze.x")))
    assert status == 500
    assert body["code"] == "BQ_WRITE_FAILED"
    assert "RuntimeError" in body["errors"][0]


def test_bq_write_skipped_when_selected_level_empty(
    gcp_project_env, good_secrets, monkeypatch
):
    """Even if campaigns/adsets have rows, if 'ads' is empty we skip BQ."""
    _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "OK", "code": "FETCH_OK",
            "records": {
                "campaigns": [{"campaign_id": "c1"}],
                "adsets": [{"adset_id": "a1"}],
                "ads": [],
            },
            "meta": {}, "errors": [],
        },
    )
    monkeypatch.setattr(
        cf_main,
        "_write_records_to_bq",
        lambda **_: (_ for _ in ()).throw(AssertionError("must not write")),
    )
    body, status = cf_main.run(_FakeRequest(_base_body(target_table="bronze.x")))
    assert status == 200
    assert body["records"] == []
    # No BQ meta keys when nothing was written.
    assert "bq_table_id" not in body["meta"]
    # But total counts still surface.
    assert body["meta"]["total_campaigns"] == 1
    assert body["meta"]["total_ads"] == 0


def test_invalid_target_table_returns_400(gcp_project_env, good_secrets, monkeypatch):
    _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "OK", "code": "FETCH_OK",
            "records": {"campaigns": [], "adsets": [], "ads": [{"ad_id": "x"}]},
            "meta": {}, "errors": [],
        },
    )
    body, status = cf_main.run(_FakeRequest(_base_body(target_table="just_table_no_dataset")))
    assert status == 400
    assert body["code"] == "INVALID_TARGET_TABLE"


# =========================================================================
# Table id resolution
# =========================================================================


def test_resolve_table_id_two_parts_prepends_project(gcp_project_env):
    assert cf_main._resolve_table_id("bronze.x") == "monks-mds-dev-test.bronze.x"


def test_resolve_table_id_three_parts_passthrough(gcp_project_env):
    assert (
        cf_main._resolve_table_id("other-proj.bronze.x")
        == "other-proj.bronze.x"
    )


def test_resolve_table_id_rejects_garbage(gcp_project_env):
    with pytest.raises(ValueError):
        cf_main._resolve_table_id("nonsense")
    with pytest.raises(ValueError):
        cf_main._resolve_table_id("a.b.c.d")
    with pytest.raises(ValueError):
        cf_main._resolve_table_id("")


# =========================================================================
# Schema derivation
# =========================================================================


def test_derive_bq_schema_uses_manifest_types_for_known_columns():
    records = [{
        "ad_id": "x1",
        "impressions": 10.0,
        "spend": "1.50",
        "date_start": "2026-05-13",
        "actions": [{"action_type": "link_click", "value": "3"}],
    }]
    schema = cf_main._derive_bq_schema(records)
    by_name = {f["name"]: f for f in schema}
    assert by_name["ad_id"]["type"] == "STRING"
    assert by_name["impressions"]["type"] == "FLOAT64"
    assert by_name["spend"]["type"] == "NUMERIC"
    assert by_name["date_start"]["type"] == "DATE"
    assert by_name["actions"]["type"] == "JSON"
    assert all(f["mode"] == "NULLABLE" for f in schema)


def test_derive_bq_schema_defaults_unknown_columns_to_string():
    records = [{"NeverHeardOf": "x", "MysteryField": 42}]
    schema = cf_main._derive_bq_schema(records)
    types_by_name = {f["name"]: f["type"] for f in schema}
    assert types_by_name == {"NeverHeardOf": "STRING", "MysteryField": "STRING"}


def test_derive_bq_schema_empty_records_returns_empty_schema():
    assert cf_main._derive_bq_schema([]) == []


# =========================================================================
# Preview cap (applied to selected subkey level)
# =========================================================================


def test_records_preview_capped_when_over_threshold(
    gcp_project_env, good_secrets, monkeypatch
):
    big_ads = [{"ad_id": f"x{i}", "impressions": i} for i in range(cf_main.RECORDS_PREVIEW_CAP + 50)]
    _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "OK", "code": "FETCH_OK",
            "records": {"campaigns": [], "adsets": [], "ads": big_ads},
            "meta": {}, "errors": [],
        },
    )
    monkeypatch.setattr(
        cf_main,
        "_write_records_to_bq",
        lambda **_: {"bq_table_id": "p.d.t", "rows_written": len(big_ads), "schema_created": False},
    )
    body, status = cf_main.run(_FakeRequest(_base_body(target_table="bronze.t")))
    assert status == 200
    assert len(body["records"]) == cf_main.RECORDS_PREVIEW_CAP
    assert body["meta"]["total_ads"] == len(big_ads)
    assert body["meta"]["records_preview_capped_at"] == cf_main.RECORDS_PREVIEW_CAP


def test_records_preview_not_capped_under_threshold(
    gcp_project_env, good_secrets, monkeypatch
):
    ads = [{"ad_id": f"x{i}"} for i in range(5)]
    _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "OK", "code": "FETCH_OK",
            "records": {"campaigns": [], "adsets": [], "ads": ads},
            "meta": {}, "errors": [],
        },
    )
    body, status = cf_main.run(_FakeRequest(_base_body()))
    assert status == 200
    assert body["records"] == ads
    assert "records_preview_capped_at" not in body["meta"]


# =========================================================================
# Project resolution
# =========================================================================


def test_gcp_project_raises_without_env(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    with pytest.raises(RuntimeError, match="GCP_PROJECT"):
        cf_main._gcp_project()


def test_gcp_project_accepts_google_cloud_project_env(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT", raising=False)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "other-proj")
    assert cf_main._gcp_project() == "other-proj"


# =========================================================================
# Manifest loading
# =========================================================================


def test_expected_manifest_id_from_bundled_manifest():
    # The conftest planted the real manifest; assert id matches.
    assert cf_main._expected_manifest_id() == "meta_facebook_ad_insights"


def test_response_subkey_defaults_to_ads():
    assert cf_main._response_subkey() == "ads"


# =========================================================================
# Ingestion timestamp (system field added by the CF)
# =========================================================================


def test_stamp_ingestion_timestamp_appends_ingested_at_to_every_record():
    from datetime import datetime, timezone

    records = [{"ad_id": "x1"}, {"ad_id": "x2"}]
    fixed = datetime(2026, 5, 21, 14, 30, 0, tzinfo=timezone.utc)
    ts = cf_main._stamp_ingestion_timestamp(records, now=fixed)
    assert ts == "2026-05-21T14:30:00+00:00"
    for r in records:
        assert r["ingested_at"] == ts


def test_stamp_ingestion_timestamp_uses_same_value_for_whole_batch():
    """All records in a single batch must share one timestamp — that's the
    contract that makes ``WHERE ingested_at = '...'`` return the exact rows
    that came in together."""
    records = [{"ad_id": f"x{i}"} for i in range(5)]
    ts = cf_main._stamp_ingestion_timestamp(records)
    stamps = {r["ingested_at"] for r in records}
    assert stamps == {ts}, "batch should share a single ingested_at value"


def test_stamp_ingestion_timestamp_places_field_last_in_key_order():
    """dict preserves insertion order in Py3.7+; the schema derivation
    iterates ``records[0].keys()`` so the last-inserted key becomes the
    last column in BQ."""
    records = [{"ad_id": "x1", "impressions": 10, "spend": "1.50"}]
    cf_main._stamp_ingestion_timestamp(records)
    assert list(records[0].keys())[-1] == "ingested_at"


def test_stamp_ingestion_timestamp_overwrites_pre_existing_value():
    """The CF is authoritative for ingested_at — if the connector or some
    upstream stuffed a value already, we replace it with our batch timestamp."""
    records = [{"ad_id": "x1", "ingested_at": "WRONG-VALUE-FROM-CONNECTOR"}]
    ts = cf_main._stamp_ingestion_timestamp(records)
    assert records[0]["ingested_at"] == ts
    assert ts != "WRONG-VALUE-FROM-CONNECTOR"


def test_stamp_ingestion_timestamp_returns_string_even_on_empty_records():
    """Useful for echo-in-meta — we want a value even when nothing was
    written, so the trace shows when the (empty) batch was processed."""
    records: list[dict] = []
    ts = cf_main._stamp_ingestion_timestamp(records)
    assert isinstance(ts, str) and ts


def test_field_type_lookup_includes_ingested_at_as_timestamp():
    assert cf_main._field_type_lookup()["ingested_at"] == "TIMESTAMP"


def test_field_type_lookup_system_field_wins_over_manifest(monkeypatch):
    """If a manifest mistakenly declared ingested_at as STRING, _SYSTEM_FIELDS
    must still force it to TIMESTAMP. Regression guard against a connector
    accidentally redefining a system column with a load-breaking type."""
    monkeypatch.setattr(
        cf_main,
        "_manifest",
        lambda: {
            "available_fields": [
                {"name": "ingested_at", "type": "STRING"},
                {"name": "ad_id", "type": "STRING"},
            ]
        },
    )
    lookup = cf_main._field_type_lookup()
    assert lookup["ingested_at"] == "TIMESTAMP"
    assert lookup["ad_id"] == "STRING"


def test_derive_bq_schema_for_stamped_records_has_ingested_at_last_as_timestamp():
    """End-to-end of the system-field contract: stamp + derive schema must
    yield ingested_at as the FINAL column with TIMESTAMP type and NULLABLE
    mode (NULLABLE because all our columns are NULLABLE for resilience)."""
    records = [{"ad_id": "x1", "impressions": 10}]
    cf_main._stamp_ingestion_timestamp(records)
    schema = cf_main._derive_bq_schema(records)
    assert schema[-1]["name"] == "ingested_at"
    assert schema[-1]["type"] == "TIMESTAMP"
    assert schema[-1]["mode"] == "NULLABLE"


def test_run_echoes_ingested_at_in_meta_when_bq_writer_returns_it(
    gcp_project_env, good_secrets, monkeypatch
):
    """The handler merges _write_records_to_bq's return dict into meta;
    ingested_at must surface so the backend can see when the batch was
    stamped without querying BQ."""
    _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "OK",
            "code": "FETCH_OK",
            "records": {"campaigns": [], "adsets": [], "ads": [{"ad_id": "x"}]},
            "meta": {},
            "errors": [],
        },
    )

    def _fake_bq(*, table_id, records):
        # Mirror the real _write_records_to_bq contract: it stamps the
        # records and echoes the timestamp it used.
        return {
            "bq_table_id": table_id,
            "rows_written": len(records),
            "schema_created": True,
            "ingested_at": "2026-05-21T14:30:00+00:00",
        }

    monkeypatch.setattr(cf_main, "_write_records_to_bq", _fake_bq)
    body, status = cf_main.run(
        _FakeRequest(_base_body(target_table="bronze.meta_facebook_ad_insights"))
    )
    assert status == 200
    assert body["meta"]["ingested_at"] == "2026-05-21T14:30:00+00:00"
