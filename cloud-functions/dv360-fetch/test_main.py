"""Unit tests for dv360-fetch Cloud Function (``main.py``).

The tests are fully hermetic: they do NOT require the
``functions-framework`` package, the ``google-cloud-*`` SDKs, or any
network access. ``conftest.py`` stubs everything before ``main`` is
imported, and each test monkeypatches ``_resolve_secret`` /
``_write_records_to_bq`` / ``dv360_fetch`` to inject deterministic
behaviour.

Coverage map
============

* Validation guards: missing tenant_id, missing manifest_id, wrong
  manifest_id, malformed params.
* Secret resolution: happy path, missing secret -> MISSING_SECRET.
* Connector errors: each known error code surfaces with the right
  HTTP status.
* Connector raises: unexpected exception wrapped in CONNECTOR_RAISED.
* BQ write: happy path with stub, target_table normalisation
  (``dataset.table`` vs ``project.dataset.table``), invalid table.
* Records preview cap.
* Schema derivation: known columns come from manifest, unknown columns
  fall back to STRING.
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
    """Plant a fake ``dv360_reports`` module into ``sys.modules``.

    ``main`` does ``from dv360_reports import fetch`` lazily inside
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
            "records": [],
            "meta": {},
            "errors": [],
        }

    stub_mod = types.ModuleType("dv360_reports")
    stub_mod.fetch = _fake_fetch
    monkeypatch.setitem(sys.modules, "dv360_reports", stub_mod)
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
        "tenant_id": "acme",
        "manifest_id": "dv360_reports",
        "manifest_version": "0.1.0",
        "params": {"data_range": "LAST_7_DAYS"},
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
    """Pretend SM returns a query_id and a valid SA JSON blob."""

    def _fake_resolve(secret_id, version="latest"):
        if secret_id.endswith("query_id"):
            return "1234567"
        if secret_id.endswith("service_account_json"):
            return '{"type":"service_account","client_email":"x@y.iam"}'
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
    body, status = cf_main.run(_FakeRequest(_base_body(manifest_id="meta_ads")))
    assert status == 400
    assert body["code"] == "MANIFEST_MISMATCH"
    assert "dv360_reports" in body["errors"][0]


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
    assert "query_id" in body["errors"][0]


def test_build_connector_context_returns_query_id_and_sa(gcp_project_env, good_secrets):
    ctx = cf_main._build_connector_context("acme")
    assert ctx["query_id"] == "1234567"
    assert "service_account_json" in ctx
    assert ctx["service_account_json"].startswith("{")


def test_secrets_named_by_tenant_id(gcp_project_env, monkeypatch):
    """tenant_id 'acme' must produce client_acme_dv360_query_id / _service_account_json."""
    seen = []

    def _fake_resolve(secret_id, version="latest"):
        seen.append(secret_id)
        return "x" if secret_id.endswith("query_id") else "{}"

    monkeypatch.setattr(cf_main, "_resolve_secret", _fake_resolve)
    cf_main._build_connector_context("acme")
    assert seen == [
        "client_acme_dv360_query_id",
        "client_acme_dv360_service_account_json",
    ]


# =========================================================================
# Connector outcome routing
# =========================================================================


@pytest.mark.parametrize(
    "connector_code, expected_status",
    [
        ("UNAUTHORIZED", 401),
        ("INVALID_CREDENTIALS", 401),
        ("MISSING_CREDENTIALS", 401),
        ("FORBIDDEN", 403),
        ("MISSING_QUERY_ID", 400),
        ("INVALID_PARAMS", 400),
        ("POLL_TIMEOUT", 504),
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
            "records": [],
            "meta": {},
            "errors": ["bork"],
        },
    )
    body, status = cf_main.run(_FakeRequest(_base_body()))
    assert status == expected_status
    assert body["code"] == connector_code
    assert body["status"] == "ERR"


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
    monkeypatch.delitem(sys.modules, "dv360_reports", raising=False)

    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def _failing_import(name, *args, **kwargs):
        if name == "dv360_reports":
            raise ImportError("no module")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _failing_import)
    body, status = cf_main.run(_FakeRequest(_base_body()))
    assert status == 500
    assert body["code"] == "CONNECTOR_NOT_PACKAGED"


# =========================================================================
# Successful round-trip without BQ write
# =========================================================================


def test_run_happy_path_no_target_table(gcp_project_env, good_secrets, monkeypatch):
    records = [{"Impressions": 10, "Clicks": 1, "Date": "2026/05/19"}]
    recorder = _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "OK",
            "code": "FETCH_OK",
            "records": records,
            "meta": {"query_id": "1234567"},
            "errors": [],
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
    assert body["records"] == records
    assert body["meta"]["records_total"] == 1
    assert body["meta"]["tenant_id"] == "acme"
    assert recorder["call_count"] == 1
    # The connector must have received a sane context.
    assert recorder["context"]["query_id"] == "1234567"


def test_fields_lifted_to_params_for_connector(gcp_project_env, good_secrets, monkeypatch):
    recorder = _install_stub_connector(monkeypatch)
    body = _base_body(fields=["Impressions", "Clicks"])
    cf_main.run(_FakeRequest(body))
    # HTTPBackend lifted ``fields`` to top-level; CF re-injects into params.
    assert recorder["params"]["fields"] == ["Impressions", "Clicks"]


# =========================================================================
# BigQuery write
# =========================================================================


def test_run_writes_to_bq_when_target_table_present(
    gcp_project_env, good_secrets, monkeypatch
):
    records = [{"Impressions": 10, "Clicks": 1, "Date": "2026/05/19"}]
    _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "OK", "code": "FETCH_OK", "records": records,
            "meta": {"query_id": "q1"}, "errors": [],
        },
    )

    seen = {}

    def _fake_bq(*, table_id, records):
        seen["table_id"] = table_id
        seen["row_count"] = len(records)
        return {"bq_table_id": table_id, "rows_written": len(records), "schema_created": True}

    monkeypatch.setattr(cf_main, "_write_records_to_bq", _fake_bq)

    body, status = cf_main.run(_FakeRequest(_base_body(target_table="bronze.dv360_reports")))
    assert status == 200
    assert body["status"] == "OK"
    assert seen["table_id"] == "monks-mds-dev-test.bronze.dv360_reports"
    assert seen["row_count"] == 1
    assert body["meta"]["bq_table_id"] == "monks-mds-dev-test.bronze.dv360_reports"
    assert body["meta"]["rows_written"] == 1
    assert body["meta"]["schema_created"] is True


def test_bq_write_failure_returns_bq_write_failed(
    gcp_project_env, good_secrets, monkeypatch
):
    _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "OK", "code": "FETCH_OK",
            "records": [{"Impressions": 1}],
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


def test_bq_write_skipped_when_records_empty(gcp_project_env, good_secrets, monkeypatch):
    _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "OK", "code": "FETCH_OK", "records": [],
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


def test_invalid_target_table_returns_400(gcp_project_env, good_secrets, monkeypatch):
    _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "OK", "code": "FETCH_OK",
            "records": [{"Impressions": 1}],
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
    records = [{"Impressions": 100, "Clicks": 5, "Date": "2026/05/19"}]
    schema = cf_main._derive_bq_schema(records)
    by_name = {f["name"]: f for f in schema}
    assert by_name["Impressions"]["type"] == "INT64"
    assert by_name["Clicks"]["type"] == "INT64"
    assert by_name["Date"]["type"] == "STRING"
    assert all(f["mode"] == "NULLABLE" for f in schema)


def test_derive_bq_schema_defaults_unknown_columns_to_string():
    records = [{"NeverHeardOf": "x", "MysteryField": 42}]
    schema = cf_main._derive_bq_schema(records)
    types_by_name = {f["name"]: f["type"] for f in schema}
    assert types_by_name == {"NeverHeardOf": "STRING", "MysteryField": "STRING"}


def test_derive_bq_schema_empty_records_returns_empty_schema():
    assert cf_main._derive_bq_schema([]) == []


# =========================================================================
# Preview cap
# =========================================================================


def test_records_preview_capped_when_over_threshold(
    gcp_project_env, good_secrets, monkeypatch
):
    big = [{"Impressions": i} for i in range(cf_main.RECORDS_PREVIEW_CAP + 50)]
    _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "OK", "code": "FETCH_OK", "records": big,
            "meta": {}, "errors": [],
        },
    )
    monkeypatch.setattr(
        cf_main,
        "_write_records_to_bq",
        lambda **_: {"bq_table_id": "p.d.t", "rows_written": len(big), "schema_created": False},
    )
    body, status = cf_main.run(_FakeRequest(_base_body(target_table="bronze.t")))
    assert status == 200
    assert len(body["records"]) == cf_main.RECORDS_PREVIEW_CAP
    assert body["meta"]["records_total"] == len(big)
    assert body["meta"]["records_preview_capped_at"] == cf_main.RECORDS_PREVIEW_CAP


def test_records_preview_not_capped_under_threshold(
    gcp_project_env, good_secrets, monkeypatch
):
    records = [{"Impressions": i} for i in range(5)]
    _install_stub_connector(
        monkeypatch,
        return_value={
            "status": "OK", "code": "FETCH_OK", "records": records,
            "meta": {}, "errors": [],
        },
    )
    body, status = cf_main.run(_FakeRequest(_base_body()))
    assert status == 200
    assert body["records"] == records
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
    assert cf_main._expected_manifest_id() == "dv360_reports"
