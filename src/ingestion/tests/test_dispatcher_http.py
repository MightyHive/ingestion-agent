"""Unit tests for ``HTTPBackend`` and the ``auto`` runtime selector.

We stub ``httpx.post`` rather than spinning up a real server so the
tests run in <100 ms and don't need network access or ADC.

Two regression themes are critical and have dedicated tests:

* **Payload never leaks credentials.** The HTTP wire payload must
  contain ``tenant_id``, ``manifest_id``, ``params`` and that is it.
  No service-account JSON, no tokens, no refresh tokens, no API keys
  — even if the caller accidentally drops them into ``params``. The
  scrubber is defence-in-depth on top of the contract that ``params``
  comes from the user-facing request body.

* **id_token fetch is skipped for loopback URLs.** This keeps smoke
  tests against the functions-framework emulator on
  ``http://localhost:8080`` working without requiring
  ``gcloud auth application-default login``.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from ingestion.auth.tenant_context import TenantContext
from ingestion.dispatcher.base import (
    AutoBackend,
    BackendError,
    ConnectorDispatcher,
)
from ingestion.dispatcher.http import (
    HTTPBackend,
    _build_payload,
    _resolve_cf_url,
    _scrub_secret_keys,
)


# --- helpers ------------------------------------------------------------


def _tenant() -> TenantContext:
    return TenantContext(
        tenant_id="acme",
        gcp_project="monks-mds-dev",
        service_account="mds@monks-mds-dev.iam.gserviceaccount.com",
        context={"query_id": "QID-123", "service_account_json": "{REDACTED}"},
    )


def _http_manifest(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "dv360_reports",
        "name": "DV360",
        "platform": "dv360",
        "connector": "reports",
        "version": "0.1.0",
        "endpoint": {
            "module_path": "dv360.reports.dv360_reports",
            "function_name": "fetch",
            "cloud_function_name": "dv360-fetch",
            "cloud_function_region": "us-central1",
        },
        "auth": {"context_required": ["query_id", "service_account_json"]},
        "params": {"required": [], "optional": []},
        "available_fields": [{"name": "Impressions", "type": "INT64"}],
        "limits": {"max_call_duration_seconds": 540},
    }
    base.update(overrides)
    return base


def _stub_post(
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: int = 200,
    body: Any = None,
    raise_exc: Exception | None = None,
    recorder: dict | None = None,
) -> None:
    """Replace ``httpx.post`` with a controllable stub.

    When ``raise_exc`` is provided it is raised instead of returning a
    response. The ``recorder`` dict, if given, is populated with the
    ``url``, ``payload``, and ``headers`` of the captured call.
    """

    def _fake_post(url: str, **kwargs: Any) -> httpx.Response:
        if recorder is not None:
            recorder["url"] = url
            recorder["payload"] = kwargs.get("json")
            recorder["headers"] = kwargs.get("headers")
            recorder["timeout"] = kwargs.get("timeout")
        if raise_exc is not None:
            raise raise_exc
        if body is None:
            content = b""
        elif isinstance(body, (bytes, bytearray)):
            content = bytes(body)
        elif isinstance(body, str):
            content = body.encode("utf-8")
        else:
            import json as _json
            content = _json.dumps(body).encode("utf-8")
        return httpx.Response(
            status_code=status,
            content=content,
            headers={"content-type": "application/json"}
            if not isinstance(body, (bytes, bytearray, str))
            else {"content-type": "text/plain"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", _fake_post)


# --- URL composition ----------------------------------------------------


def test_resolve_cf_url_uses_env_override_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MDS_CF_BASE_URL", "http://localhost:9999")
    url = _resolve_cf_url(
        cf_name="dv360-fetch", region="us-central1", gcp_project="acme-prod"
    )
    assert url == "http://localhost:9999/dv360-fetch"


def test_resolve_cf_url_strips_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MDS_CF_BASE_URL", "http://localhost:9999/")
    url = _resolve_cf_url(
        cf_name="dv360-fetch", region="us-central1", gcp_project="acme-prod"
    )
    assert url == "http://localhost:9999/dv360-fetch"


def test_resolve_cf_url_falls_back_to_canonical_gcf_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MDS_CF_BASE_URL", raising=False)
    url = _resolve_cf_url(
        cf_name="dv360-fetch", region="us-central1", gcp_project="monks-mds-dev"
    )
    assert url == "https://us-central1-monks-mds-dev.cloudfunctions.net/dv360-fetch"


def test_resolve_cf_url_raises_when_project_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MDS_CF_BASE_URL", raising=False)
    with pytest.raises(BackendError, match="connector_url_unresolved"):
        _resolve_cf_url(cf_name="dv360-fetch", region="us-central1", gcp_project=None)


# --- payload scrubber ---------------------------------------------------


def test_scrub_secret_keys_drops_top_level_credentials() -> None:
    cleaned = _scrub_secret_keys(
        {
            "fields": ["Impressions"],
            "service_account_json": "{...}",
            "access_token": "ya29...",
            "refresh_token": "1//abc",
            "api_key": "sk-...",
            "data_range": "LAST_7_DAYS",
        }
    )
    assert cleaned == {"fields": ["Impressions"], "data_range": "LAST_7_DAYS"}


def test_scrub_secret_keys_drops_nested_credentials() -> None:
    cleaned = _scrub_secret_keys(
        {
            "params": {
                "data_range": "LAST_7_DAYS",
                "credentials": {"private_key": "MIIE..."},
            },
            "items": [{"client_secret": "x", "id": 1}],
        }
    )
    assert cleaned == {
        "params": {"data_range": "LAST_7_DAYS"},
        "items": [{"id": 1}],
    }


def test_scrub_is_case_insensitive_and_substring_based() -> None:
    cleaned = _scrub_secret_keys(
        {"ServiceAccountJSON": "x", "AccessToken": "y", "Foo": "z"}
    )
    assert cleaned == {"Foo": "z"}


# --- payload construction ----------------------------------------------


def test_build_payload_lifts_fields_and_target_table_to_top_level() -> None:
    payload = _build_payload(
        manifest=_http_manifest(),
        params={
            "fields": ["Impressions", "Clicks"],
            "data_range": "LAST_7_DAYS",
            "target_table": "bronze.dv360_acme",
        },
        tenant=_tenant(),
    )
    assert payload["tenant_id"] == "acme"
    assert payload["manifest_id"] == "dv360_reports"
    assert payload["manifest_version"] == "0.1.0"
    assert payload["fields"] == ["Impressions", "Clicks"]
    assert payload["target_table"] == "bronze.dv360_acme"
    assert payload["params"] == {"data_range": "LAST_7_DAYS"}


def test_build_payload_never_contains_secrets() -> None:
    """Regression: even if a caller stuffs secrets into params, the
    wire payload must not carry them."""
    payload = _build_payload(
        manifest=_http_manifest(),
        params={
            "fields": ["Impressions"],
            "data_range": "LAST_7_DAYS",
            "service_account_json": "{LEAKED}",
            "access_token": "ya29.LEAKED",
            "refresh_token": "1//LEAKED",
            "client_secret": "leaked",
        },
        tenant=_tenant(),
    )
    flat = repr(payload)
    assert "LEAKED" not in flat
    assert "service_account_json" not in flat
    assert "access_token" not in flat
    assert "refresh_token" not in flat
    assert "client_secret" not in flat


# --- HTTPBackend happy + error paths -----------------------------------


def test_http_backend_happy_path_skips_id_token_on_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MDS_CF_BASE_URL", "http://localhost:9999")
    recorder: dict = {}
    _stub_post(
        monkeypatch,
        status=200,
        body={
            "status": "ok",
            "code": 200,
            "records": [{"Impressions": 12}],
            "meta": {"row_count": 1},
            "errors": [],
        },
        recorder=recorder,
    )

    resp = HTTPBackend().invoke(
        _http_manifest(),
        {"fields": ["Impressions"], "data_range": "LAST_7_DAYS"},
        _tenant(),
    )

    assert resp.status == "ok"
    assert resp.code == 200
    assert resp.records == [{"Impressions": 12}]
    assert resp.meta == {"row_count": 1}
    assert resp.diagnostics["backend"] == "http"
    assert resp.diagnostics["http_status"] == 200
    assert resp.diagnostics["url"] == "http://localhost:9999/dv360-fetch"
    # Loopback ⇒ no Authorization header (test runs without ADC)
    assert "Authorization" not in recorder["headers"]
    # Payload sanity
    assert recorder["payload"]["tenant_id"] == "acme"
    assert recorder["payload"]["manifest_id"] == "dv360_reports"


def test_http_backend_missing_cf_name_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MDS_CF_BASE_URL", "http://localhost:9999")
    manifest = _http_manifest()
    manifest["endpoint"].pop("cloud_function_name")
    with pytest.raises(BackendError, match="cloud_function_name"):
        HTTPBackend().invoke(manifest, {"fields": []}, _tenant())


@pytest.mark.parametrize(
    "status, expected_prefix",
    [
        (401, "connector_auth_required"),
        (403, "connector_forbidden"),
        (404, "connector_not_found"),
        (408, "connector_timeout"),
        (504, "connector_timeout"),
        (500, "connector_upstream_error"),
        (502, "connector_upstream_error"),
        (503, "connector_upstream_error"),
    ],
)
def test_http_backend_maps_http_errors(
    monkeypatch: pytest.MonkeyPatch, status: int, expected_prefix: str
) -> None:
    monkeypatch.setenv("MDS_CF_BASE_URL", "http://localhost:9999")
    _stub_post(monkeypatch, status=status, body={"error": "boom"})
    with pytest.raises(BackendError, match=expected_prefix):
        HTTPBackend().invoke(
            _http_manifest(),
            {"fields": ["Impressions"], "data_range": "LAST_7_DAYS"},
            _tenant(),
        )


def test_http_backend_maps_timeout_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MDS_CF_BASE_URL", "http://localhost:9999")
    _stub_post(
        monkeypatch,
        raise_exc=httpx.ReadTimeout("read"),
    )
    with pytest.raises(BackendError, match="connector_timeout"):
        HTTPBackend().invoke(
            _http_manifest(),
            {"fields": ["Impressions"], "data_range": "LAST_7_DAYS"},
            _tenant(),
        )


def test_http_backend_maps_connect_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MDS_CF_BASE_URL", "http://localhost:9999")
    _stub_post(monkeypatch, raise_exc=httpx.ConnectError("refused"))
    with pytest.raises(BackendError, match="connector_unreachable"):
        HTTPBackend().invoke(
            _http_manifest(),
            {"fields": ["Impressions"], "data_range": "LAST_7_DAYS"},
            _tenant(),
        )


def test_http_backend_non_json_body_is_structured_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MDS_CF_BASE_URL", "http://localhost:9999")
    _stub_post(monkeypatch, status=200, body=b"this is not json")
    with pytest.raises(BackendError, match="connector_invalid_response"):
        HTTPBackend().invoke(
            _http_manifest(),
            {"fields": ["Impressions"], "data_range": "LAST_7_DAYS"},
            _tenant(),
        )


def test_http_backend_resolves_timeout_from_manifest_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MDS_CF_BASE_URL", "http://localhost:9999")
    recorder: dict = {}
    _stub_post(
        monkeypatch,
        status=200,
        body={"status": "ok", "code": 200, "records": [], "meta": {}, "errors": []},
        recorder=recorder,
    )
    manifest = _http_manifest()
    manifest["limits"] = {"max_call_duration_seconds": 60}
    HTTPBackend().invoke(
        manifest, {"fields": [], "data_range": "LAST_7_DAYS"}, _tenant()
    )
    # 60 + 20s client buffer
    assert recorder["timeout"] == 80


# --- context_required bypass (Phase 5 refactor) ------------------------
#
# These tests pin the contract change: ``auth.context_required`` is no
# longer enforced by the dispatcher or by HTTPBackend, because the CF
# resolves its own secrets from Secret Manager. The validation lives in
# LocalBackend only. See ``base.py`` docstring on ConnectorDispatcher.invoke.


def test_http_backend_does_not_validate_context_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTPBackend must NOT raise MissingContextKeyError even when the
    manifest declares context_required and the tenant context is empty.
    The CF resolves its own secrets via Secret Manager, so the MDS
    backend has no reason to require placeholder values in tenants.json.
    """
    monkeypatch.setenv("MDS_CF_BASE_URL", "http://localhost:9999")
    _stub_post(
        monkeypatch,
        status=200,
        body={"status": "ok", "code": 200, "records": [], "meta": {}, "errors": []},
    )

    bare_tenant = TenantContext(
        tenant_id="acme",
        gcp_project="monks-mds-dev",
        service_account="mds@monks-mds-dev.iam.gserviceaccount.com",
        context={},  # no credentials at all
    )
    manifest = _http_manifest()
    # Sanity: the manifest under test actually declares required keys.
    assert manifest["auth"]["context_required"] == [
        "query_id",
        "service_account_json",
    ]

    resp = HTTPBackend().invoke(
        manifest, {"fields": ["Impressions"], "data_range": "LAST_7_DAYS"}, bare_tenant
    )
    assert resp.status == "ok"


def test_auto_backend_with_cf_routes_to_http_without_context_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ConnectorDispatcher(runtime='auto') with an HTTP-bound manifest
    (i.e. cloud_function_name present) must reach the HTTP path even if
    tenant.context is empty. AutoBackend is just a delegate, so the
    bypass is inherited from HTTPBackend.
    """
    monkeypatch.setenv("MDS_CF_BASE_URL", "http://localhost:9999")
    recorder: dict = {}
    _stub_post(
        monkeypatch,
        status=200,
        body={"status": "ok", "code": 200, "records": [], "meta": {}, "errors": []},
        recorder=recorder,
    )

    bare_tenant = TenantContext(
        tenant_id="acme",
        gcp_project="monks-mds-dev",
        service_account="mds@monks-mds-dev.iam.gserviceaccount.com",
        context={},
    )
    disp = ConnectorDispatcher(runtime="auto")
    resp = disp.invoke(
        _http_manifest(),
        {"fields": ["Impressions"], "data_range": "LAST_7_DAYS"},
        bare_tenant,
    )
    assert resp.status == "ok"
    # The stub captured the call — confirms we went through HTTPBackend.
    assert recorder["url"] == "http://localhost:9999/dv360-fetch"


# --- runtime selection --------------------------------------------------


def test_dispatcher_http_runtime_builds_http_backend() -> None:
    disp = ConnectorDispatcher(runtime="http")
    assert isinstance(disp.backend, HTTPBackend)


def test_dispatcher_auto_runtime_builds_auto_backend() -> None:
    disp = ConnectorDispatcher(runtime="auto")
    assert isinstance(disp.backend, AutoBackend)


def test_auto_backend_routes_http_when_cf_name_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MDS_CF_BASE_URL", "http://localhost:9999")
    recorder: dict = {}
    _stub_post(
        monkeypatch,
        status=200,
        body={"status": "ok", "code": 200, "records": [], "meta": {}, "errors": []},
        recorder=recorder,
    )

    disp = ConnectorDispatcher(runtime="auto")
    disp.invoke(
        _http_manifest(),
        {"fields": ["Impressions"], "data_range": "LAST_7_DAYS"},
        _tenant(),
    )

    # Routed via HTTP — the stub captured the call.
    assert recorder["url"] == "http://localhost:9999/dv360-fetch"


def test_auto_backend_routes_local_when_cf_name_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # If the manifest has no cloud_function_name, AutoBackend uses
    # LocalBackend, which will then attempt to import the module. We
    # don't have to actually load a real module here — we only assert
    # that HTTPBackend was NOT called by stubbing httpx.post to blow
    # up if it ever runs.
    def _explode(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("HTTPBackend must not be invoked when cf_name absent")

    monkeypatch.setattr(httpx, "post", _explode)

    manifest = _http_manifest()
    manifest["endpoint"].pop("cloud_function_name")
    # Point module_path at something that will fail to import — we
    # only care that the routing reached LocalBackend.
    manifest["endpoint"]["module_path"] = "definitely.not.a.module"
    manifest["auth"]["context_required"] = ["query_id", "service_account_json"]

    disp = ConnectorDispatcher(runtime="auto")
    with pytest.raises(BackendError, match="not importable"):
        disp.invoke(manifest, {"fields": []}, _tenant())
