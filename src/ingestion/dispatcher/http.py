"""HTTPBackend — invokes connectors deployed as Google Cloud Functions over HTTPS.

Phase 5 production path. Counterpart to :class:`LocalBackend`:

* :class:`LocalBackend` imports the connector module in-process and calls
  ``fetch(params, context)`` directly. The backend has full access to the
  tenant context, including secrets (service account JSON, refresh tokens,
  etc.) because the CPython runtime is the trust boundary.

* :class:`HTTPBackend` POSTs to a Cloud Function URL. The CF is the trust
  boundary: it resolves the tenant's secrets from Secret Manager itself
  using its own service-account identity. The MDS backend never reads,
  forwards, or otherwise touches the per-tenant credential payload — it
  only sends ``{tenant_id, manifest_id, fields, params, target_table}``.
  That regression is enforced by a unit test in
  ``test_dispatcher_http.py::test_payload_never_contains_secrets``.

URL composition
---------------
The manifest declares::

    "endpoint": {
        "cloud_function_name":   "dv360-fetch",
        "cloud_function_region": "us-central1",
        ...
    }

The URL is built as:

* If ``MDS_CF_BASE_URL`` is set (local dev / staging emulator), it wins:
  ``{MDS_CF_BASE_URL}/{cloud_function_name}``.
* Otherwise the GCF gen2 canonical form:
  ``https://{region}-{tenant.gcp_project}.cloudfunctions.net/{name}``.

The project segment comes from ``tenant.gcp_project`` so a single MDS
deployment can target Cloud Functions across multiple GCP projects, one
per tenant (post-MVP — in the Phase 5 MVP all tenants share
``monks-mds-dev``).

Authentication
--------------
The CF is deployed with ``--no-allow-unauthenticated``, so every request
needs a signed Google id_token whose audience equals the CF URL. We
fetch the token with ``google.oauth2.id_token.fetch_id_token``, which
uses ADC (Application Default Credentials) on the calling machine. In
local dev, ADC resolves to the user account from
``gcloud auth application-default login`` (B0). In Cloud Run/GKE
deployments it would resolve to the attached service account.

The id_token fetch is skipped when the resolved URL points at a
loopback host (``localhost``, ``127.0.0.1``) so smoke tests and the
functions-framework emulator don't require real credentials.

Error mapping
-------------
Every failure surfaces as :class:`BackendError`. The dispatcher caller
only needs to catch one exception type. Mapping:

============  ============================================
HTTP status   BackendError message prefix
============  ============================================
401           ``connector_auth_required`` — id_token rejected
403           ``connector_forbidden`` — CF IAM denied caller
404           ``connector_not_found`` — wrong URL / CF undeployed
408, 504      ``connector_timeout``
5xx (others)  ``connector_upstream_error``
============  ============================================

Network-level failures (httpx ``TimeoutException``, ``ConnectError``,
``RequestError``) are also wrapped with the appropriate prefix so the
caller's error-handling logic is uniform.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from ingestion.auth.tenant_context import TenantContext
from ingestion.dispatcher.base import (
    BackendBase,
    BackendError,
    ConnectorResponse,
)

# Default request timeout used when the manifest does not declare one.
# Chosen to match the upper bound of a Cloud Function gen2 (9 minutes)
# plus a small client-side margin so the server-side timeout fires first
# and we get a structured error rather than a client abort.
DEFAULT_REQUEST_TIMEOUT_SEC = 560

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


class HTTPBackend(BackendBase):
    """POSTs to the connector's Cloud Function URL with a signed id_token.

    The backend is stateless. It re-resolves the URL, fetches a fresh
    id_token (Google caches under the hood when valid), and issues the
    request per call. A single instance is fine for the process
    lifetime.
    """

    name = "http"

    def invoke(
        self,
        manifest: dict[str, Any],
        params: dict[str, Any],
        tenant: TenantContext,
    ) -> ConnectorResponse:
        endpoint = manifest.get("endpoint") or {}
        cf_name = endpoint.get("cloud_function_name")
        if not cf_name:
            raise BackendError(
                f"manifest '{manifest.get('id')}' has no endpoint.cloud_function_name "
                f"— HTTPBackend cannot route the request. Add the field or set "
                f"MDS_RUNTIME=local."
            )

        url = _resolve_cf_url(
            cf_name=cf_name,
            region=endpoint.get("cloud_function_region", "us-central1"),
            gcp_project=tenant.gcp_project,
        )

        payload = _build_payload(
            manifest=manifest,
            params=params,
            tenant=tenant,
        )

        headers = {"Content-Type": "application/json"}
        if not _is_loopback(url):
            try:
                token = _fetch_id_token(url)
            except Exception as exc:  # noqa: BLE001 — one trap point
                raise BackendError(
                    f"connector_auth_unavailable: could not fetch id_token for "
                    f"audience '{url}': {type(exc).__name__}: {exc}. "
                    f"Run 'gcloud auth application-default login' to set ADC."
                ) from exc
            headers["Authorization"] = f"Bearer {token}"

        timeout_sec = _resolve_timeout(manifest)

        diagnostics: dict[str, Any] = {
            "backend": self.name,
            "url": url,
            "cloud_function_name": cf_name,
            "tenant_id": tenant.tenant_id,
            "timeout_sec": timeout_sec,
        }
        started = time.monotonic()
        try:
            response = httpx.post(
                url, json=payload, headers=headers, timeout=timeout_sec
            )
        except httpx.TimeoutException as exc:
            diagnostics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
            raise BackendError(
                f"connector_timeout: no response from '{url}' "
                f"within {timeout_sec}s ({type(exc).__name__})."
            ) from exc
        except httpx.ConnectError as exc:
            diagnostics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
            raise BackendError(
                f"connector_unreachable: could not connect to '{url}': {exc}."
            ) from exc
        except httpx.RequestError as exc:
            diagnostics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
            raise BackendError(
                f"connector_request_error: {type(exc).__name__} contacting "
                f"'{url}': {exc}."
            ) from exc

        diagnostics["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        diagnostics["http_status"] = response.status_code

        if response.status_code >= 400:
            _raise_for_http_error(response, url)

        try:
            raw = response.json()
        except ValueError as exc:
            raise BackendError(
                f"connector_invalid_response: '{url}' returned non-JSON body "
                f"(status {response.status_code}, {len(response.content)} bytes)."
            ) from exc

        return ConnectorResponse.from_dict(raw, diagnostics=diagnostics)


# --- helpers ------------------------------------------------------------


def _resolve_cf_url(*, cf_name: str, region: str, gcp_project: str | None) -> str:
    """Build the absolute URL for the Cloud Function.

    Env override (``MDS_CF_BASE_URL``) wins so the functions-framework
    emulator on ``http://localhost:8080`` is reachable without changing
    any manifest.
    """
    base = os.environ.get("MDS_CF_BASE_URL", "").rstrip("/")
    if base:
        return f"{base}/{cf_name}"
    if not gcp_project:
        raise BackendError(
            "connector_url_unresolved: tenant.gcp_project is empty and "
            "MDS_CF_BASE_URL is unset; cannot build CF URL."
        )
    return f"https://{region}-{gcp_project}.cloudfunctions.net/{cf_name}"


def _is_loopback(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in _LOOPBACK_HOSTS


def _fetch_id_token(audience: str) -> str:
    """Get an OIDC id_token whose ``aud`` claim equals ``audience``.

    Resolution order:
    1. ImpersonatedCredentials (ADC with --impersonate-service-account)
       — uses IDTokenCredentials.
    2. ServiceAccountCredentials (GOOGLE_APPLICATION_CREDENTIALS key file)
       or GCE/CloudRun metadata server — uses id_token.fetch_id_token.
    3. gcloud CLI fallback: ``gcloud auth print-identity-token``
       — works with regular user credentials (gcloud auth login /
       application-default login) on developer laptops where the Python
       SDK cannot exchange user tokens for id_tokens directly.
    """
    import google.auth  # type: ignore
    from google.auth.transport.requests import Request  # type: ignore

    credentials, _ = google.auth.default()

    # Path 1 — ImpersonatedCredentials
    try:
        from google.auth.impersonated_credentials import (  # type: ignore
            Credentials as _ImpersonatedCreds,
            IDTokenCredentials,
        )
        if isinstance(credentials, _ImpersonatedCreds):
            id_creds = IDTokenCredentials(
                credentials, target_audience=audience, include_email=True
            )
            id_creds.refresh(Request())
            return id_creds.token
    except ImportError:
        pass

    # Path 2 — service account key file or metadata server
    try:
        from google.oauth2 import id_token  # type: ignore
        return id_token.fetch_id_token(Request(), audience)
    except Exception:  # noqa: BLE001 — fall through to gcloud CLI
        pass

    # Path 3 — gcloud CLI with SA impersonation (developer laptops).
    # ``gcloud auth print-identity-token --audiences=URL`` requires a service
    # account; user credentials can't set a custom audience directly.
    # The workaround is to impersonate a SA that has cloudfunctions.invoker,
    # controlled by the ``MDS_CF_INVOKER_SA`` env var.
    invoker_sa = os.environ.get("MDS_CF_INVOKER_SA", "").strip()
    if invoker_sa:
        try:
            result = subprocess.run(
                [
                    "gcloud", "auth", "print-identity-token",
                    f"--impersonate-service-account={invoker_sa}",
                    f"--audiences={audience}",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            token = result.stdout.strip()
            if token:
                return token
        except subprocess.CalledProcessError as exc:
            raise BackendError(
                f"connector_auth_unavailable: could not fetch id_token for "
                f"audience '{audience}' via gcloud impersonation of '{invoker_sa}': "
                f"{exc.stderr.strip()}. "
                f"Make sure your account has roles/iam.serviceAccountTokenCreator on that SA."
            ) from exc

    raise BackendError(
        f"connector_auth_unavailable: could not obtain an id_token for "
        f"audience '{audience}'. "
        f"Set MDS_CF_INVOKER_SA=<sa-email> in .env to use gcloud SA impersonation, "
        f"or set GOOGLE_APPLICATION_CREDENTIALS to a service account key file."
    )


def _build_payload(
    *,
    manifest: dict[str, Any],
    params: dict[str, Any],
    tenant: TenantContext,
) -> dict[str, Any]:
    """Construct the JSON body sent to the Cloud Function.

    SECURITY: this payload must never include credentials, secrets, or
    raw ``tenant.context``. The CF resolves those itself from Secret
    Manager using its own SA identity. The regression test
    ``test_payload_never_contains_secrets`` enforces this.
    """
    # ``fields``, ``target_table``, and ``connection_id`` are first-class
    # keys at the top level so the CF can read them without reaching into
    # ``params``. Everything else goes through verbatim (after the
    # secret-scrubber — defence-in-depth, params should never contain
    # secrets because they come from the request body, not Secret Manager).
    safe_params = _scrub_secret_keys(params)
    fields = safe_params.pop("fields", None)
    target_table = safe_params.pop("target_table", None)
    connection_id = safe_params.pop("connection_id", None)

    payload: dict[str, Any] = {
        "tenant_id": tenant.tenant_id,
        "manifest_id": manifest.get("id"),
        "manifest_version": manifest.get("version"),
        "params": safe_params,
    }
    if fields is not None:
        payload["fields"] = fields
    if target_table is not None:
        payload["target_table"] = target_table
    if connection_id is not None:
        payload["connection_id"] = connection_id
    return payload


# Keys that are never allowed to traverse the wire. The CF resolves all
# of these from Secret Manager itself. Match is case-insensitive on a
# substring basis so e.g. ``serviceAccountJson`` and ``access_token``
# are both blocked.
_FORBIDDEN_KEY_FRAGMENTS = (
    "secret",
    "token",
    "password",
    "passwd",
    "credential",
    "service_account",
    "serviceaccount",
    "private_key",
    "refresh",
    "client_secret",
    "api_key",
    "apikey",
)


def _scrub_secret_keys(data: Any) -> Any:
    """Recursively strip any key whose name suggests a credential.

    Returns a deep copy with offending keys removed (not redacted) so
    they can never be observed by a network sniffer or appear in
    server-side logs of the CF request body.
    """
    if isinstance(data, dict):
        cleaned: dict[str, Any] = {}
        for k, v in data.items():
            lk = str(k).lower()
            if any(frag in lk for frag in _FORBIDDEN_KEY_FRAGMENTS):
                continue
            cleaned[k] = _scrub_secret_keys(v)
        return cleaned
    if isinstance(data, list):
        return [_scrub_secret_keys(v) for v in data]
    return data


def _resolve_timeout(manifest: dict[str, Any]) -> int:
    """Pick a client-side request timeout that just outlasts the CF.

    Manifests may declare ``limits.max_call_duration_seconds`` to
    communicate the upper bound the connector itself respects. We add a
    20s buffer so the server-side timeout fires first and we receive a
    structured error rather than an arbitrary httpx abort.
    """
    limits = manifest.get("limits") or {}
    server_timeout = limits.get("max_call_duration_seconds")
    if isinstance(server_timeout, (int, float)) and server_timeout > 0:
        return int(server_timeout) + 20
    return DEFAULT_REQUEST_TIMEOUT_SEC


def _raise_for_http_error(response: httpx.Response, url: str) -> None:
    """Translate an HTTP error response into a :class:`BackendError`.

    Best-effort: tries to surface the upstream JSON body (``errors`` or
    ``message`` keys) so users can debug from the dispatcher trace
    without having to find the CF log entry.
    """
    status = response.status_code
    body_excerpt = _excerpt_body(response)

    if status == 401:
        prefix = "connector_auth_required"
    elif status == 403:
        prefix = "connector_forbidden"
    elif status == 404:
        prefix = "connector_not_found"
    elif status in (408, 504):
        prefix = "connector_timeout"
    elif 500 <= status < 600:
        prefix = "connector_upstream_error"
    else:
        prefix = "connector_http_error"

    raise BackendError(
        f"{prefix}: '{url}' returned HTTP {status}. {body_excerpt}"
    )


def _excerpt_body(response: httpx.Response) -> str:
    """Pull a short, log-safe excerpt from a CF response body."""
    try:
        data = response.json()
    except ValueError:
        text = (response.text or "").strip()
        return f"body[{len(text)}]={text[:300]!r}" if text else "body=<empty>"
    if isinstance(data, dict):
        for key in ("error", "errors", "message", "detail"):
            if key in data:
                return f"{key}={data[key]!r}"
        return f"json_keys={sorted(data.keys())!r}"
    return f"json_type={type(data).__name__}"


__all__ = ["DEFAULT_REQUEST_TIMEOUT_SEC", "HTTPBackend"]
