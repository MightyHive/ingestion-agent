"""
FastAPI HTTP surface for the MDS ingestion platform.

Run from the ``src/`` directory:

  cd src && uvicorn api:app --reload --host 0.0.0.0 --port 8000

Or from the repo root with ``pythonpath = src`` (set in ``pytest.ini``):

  uvicorn api:app --reload --host 0.0.0.0 --port 8000

Stable endpoints (Phase 4+)
---------------------------
* ``GET  /api/catalog``            — list of connector manifests in the
                                     ``connectors-library`` submodule.
* ``GET  /api/catalog/{id}``       — full manifest for a single connector.
* ``POST /api/run``                — deterministic ingestion run. Sync JSON
                                     response. Status ``200`` on OK/WARN,
                                     ``400`` on validation error, ``502`` on
                                     connector failure, ``500`` on unexpected
                                     error. Every response carries an
                                     ``X-Request-Id`` header for tracing.

The legacy multi-agent LLM endpoints (``/api/chat``, ``/api/submit_input``,
``/api/templates``, ``/api/sessions/{id}/history``) were removed in Phase 4
together with the agent source code. Refer to git tag ``legacy-mds-agents``
if you need the historical implementation.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from auth import (
    InvalidApiKeyError,
    MissingUserError,
    TenantAccessDeniedError,
    UnknownUserError,
    assert_tenant_allowed,
    auth_is_disabled,
    load_user_tenant_registry,
    resolve_user_id,
)
from mds_env import load_mds_env

load_mds_env()

from credentials import init_db
from credentials import oauth as oauth_service
from credentials import resolve_for_run
from credentials import service as credentials_service
from credentials.exceptions import (
    ConnectionInactiveError,
    ConnectionNotFoundError,
    ConnectionProviderMismatchError,
    InvalidStatusTransitionError,
    SecretManagerError,
    SecretPayloadError,
)
from credentials.oauth.exceptions import InvalidOAuthStateError, OAuthProviderError
from credentials.schemas import ConnectionRecord, ConnectionStatus
from ingestion import build_graph
from ingestion.manifest import (
    CATALOG_API_VERSION,
    ManifestValidationError,
    get_default_catalog,
)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Initialize process-level resources once per app startup."""

    init_db()
    yield


app = FastAPI(title="MDS API", version="2.0.0", lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class RunRequest(BaseModel):
    """Request body for ``POST /api/run`` (deterministic ingestion).

    Maps 1:1 to the inputs of :class:`ingestion.state.IngestionState`. The
    catalog of valid ``manifest_id`` values is served by ``GET /api/catalog``;
    the valid keys for ``params`` (including the ``one_of`` constraints and
    the required ``fields`` entry) are documented per manifest in
    ``GET /api/catalog/{id}``.
    """

    manifest_id: str = Field(
        ...,
        min_length=1,
        description="Globally unique manifest id as exposed by GET /api/catalog.",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Connector parameters. Must include 'fields' (list of selectable "
            "available_fields names; empty list means 'all selectable'). "
            "Other keys must match the manifest's params schema."
        ),
    )
    connection_id: str = Field(
        ...,
        min_length=1,
        description="Stable connection id to resolve tenant credentials.",
    )


class CredentialUpsertRequest(BaseModel):
    """Request body for creating/updating one credential connection."""

    payload: dict[str, Any] | str = Field(
        ...,
        description="Secret payload (token string or JSON object).",
    )
    name: str | None = Field(
        default=None,
        description="Optional display name for this connection.",
    )


class CredentialStatusPatchRequest(BaseModel):
    """Request body for updating lifecycle status."""

    status: ConnectionStatus


class CredentialResponse(BaseModel):
    """Response model for connection metadata (no secret payload)."""

    connection_id: str
    tenant_id: str
    provider: str
    secret_id: str
    status: ConnectionStatus
    name: str | None = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------

# Mapping from failing-node id → (HTTP status, error key). Keeps the handler
# branchless and makes it trivial to add new failure modes (e.g. for the
# ``data_architect`` node) in later phases without touching the handler body.
_ERR_NODE_TO_HTTP: dict[str, tuple[int, str]] = {
    "request_validator": (400, "validation_failed"),
    "connector_runner": (502, "connector_failed"),
}


def _error_response(
    *,
    request_id: str,
    status_code: int,
    error_key: str,
    node: str | None = None,
    reason: str | None = None,
    details: list[str] | None = None,
) -> JSONResponse:
    """Uniform error envelope. ``X-Request-Id`` is the trace key for the run."""
    payload: dict[str, Any] = {
        "error": error_key,
        "request_id": request_id,
    }
    if node:
        payload["node"] = node
    if reason:
        payload["reason"] = reason
    if details:
        payload["details"] = details
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers={"X-Request-Id": request_id},
    )


def _tenant_or_error(
    *, request_id: str, tenant_id: str | None
) -> tuple[str | None, JSONResponse | None]:
    """Validate tenant header and return either tenant or error response."""

    value = (tenant_id or "").strip()
    if value:
        return value, None
    return None, _error_response(
        request_id=request_id,
        status_code=400,
        error_key="missing_tenant_header",
        reason="missing or empty X-Tenant-Id header",
    )


def _auth_error_response(request_id: str, exc: Exception) -> JSONResponse:
    """Map auth-layer errors to API responses."""

    if isinstance(exc, MissingUserError):
        return _error_response(
            request_id=request_id,
            status_code=401,
            error_key="missing_user",
            reason=str(exc),
        )
    if isinstance(exc, InvalidApiKeyError):
        return _error_response(
            request_id=request_id,
            status_code=401,
            error_key="invalid_api_key",
            reason=str(exc),
        )
    if isinstance(exc, UnknownUserError):
        return _error_response(
            request_id=request_id,
            status_code=403,
            error_key="unknown_user",
            reason=str(exc),
        )
    if isinstance(exc, TenantAccessDeniedError):
        return _error_response(
            request_id=request_id,
            status_code=403,
            error_key="tenant_forbidden",
            reason=str(exc),
        )
    return _error_response(
        request_id=request_id,
        status_code=500,
        error_key="internal",
        reason=str(exc) or exc.__class__.__name__,
    )


def _oauth_error_response(request_id: str, exc: Exception) -> JSONResponse:
    """Map OAuth errors to API responses."""

    if isinstance(exc, InvalidOAuthStateError):
        return _error_response(
            request_id=request_id,
            status_code=400,
            error_key="invalid_oauth_state",
            reason=str(exc),
        )
    if isinstance(exc, OAuthProviderError):
        return _error_response(
            request_id=request_id,
            status_code=400,
            error_key="oauth_provider_failed",
            reason=str(exc),
        )
    return _error_response(
        request_id=request_id,
        status_code=500,
        error_key="internal",
        reason=str(exc) or exc.__class__.__name__,
    )


def _resolve_tenant_access(
    *,
    request_id: str,
    tenant_id: str | None,
    x_user_id: str | None,
    authorization: str | None,
) -> tuple[str | None, str | None, JSONResponse | None]:
    """Resolve tenant + user access for tenant-scoped endpoints."""

    tenant, tenant_err = _tenant_or_error(request_id=request_id, tenant_id=tenant_id)
    if tenant_err is not None:
        return None, None, tenant_err

    if auth_is_disabled():
        return tenant, "auth_disabled", None

    try:
        registry = load_user_tenant_registry()
        user_id = resolve_user_id(
            x_user_id=x_user_id,
            authorization=authorization,
            registry=registry,
        )
        assert_tenant_allowed(user_id=user_id, tenant_id=tenant, registry=registry)
    except Exception as exc:
        return None, None, _auth_error_response(request_id, exc)
    return tenant, user_id, None


def _connection_payload(record: ConnectionRecord) -> dict[str, Any]:
    """Serialize connection record for API JSON responses."""

    return {
        "connection_id": record.connection_id,
        "tenant_id": record.tenant_id,
        "provider": record.provider,
        "secret_id": record.secret_id,
        "status": record.status.value,
        "name": record.name,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def _credentials_error_response(request_id: str, exc: Exception) -> JSONResponse:
    """Map credentials domain errors to HTTP status codes."""

    if isinstance(exc, SecretPayloadError):
        return _error_response(
            request_id=request_id,
            status_code=400,
            error_key="invalid_payload",
            reason=str(exc),
        )
    if isinstance(exc, ConnectionNotFoundError):
        return _error_response(
            request_id=request_id,
            status_code=404,
            error_key="connection_not_found",
            reason=str(exc),
        )
    if isinstance(exc, ConnectionInactiveError):
        return _error_response(
            request_id=request_id,
            status_code=409,
            error_key="connection_inactive",
            reason=str(exc),
        )
    if isinstance(exc, InvalidStatusTransitionError):
        return _error_response(
            request_id=request_id,
            status_code=409,
            error_key="invalid_status_transition",
            reason=str(exc),
        )
    if isinstance(exc, ConnectionProviderMismatchError):
        return _error_response(
            request_id=request_id,
            status_code=400,
            error_key="provider_mismatch",
            reason=str(exc),
        )
    if isinstance(exc, SecretManagerError):
        return _error_response(
            request_id=request_id,
            status_code=502,
            error_key="secret_manager_failed",
            reason=str(exc),
        )
    return _error_response(
        request_id=request_id,
        status_code=500,
        error_key="internal",
        reason=str(exc) or exc.__class__.__name__,
    )


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def _request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Pydantic intercepts malformed bodies before our handler runs, so by
    default the 422 response has no ``X-Request-Id`` header. The frontend
    contract (``docs/api.md`` §3.3) promises a trace id on *every* response,
    so we re-emit the 422 with one. The body keeps the Pydantic ``errors()``
    shape so existing tooling that parses it doesn't break.
    """
    request_id = str(uuid.uuid4())
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "request_id": request_id},
        headers={"X-Request-Id": request_id},
    )


# ---------------------------------------------------------------------------
# Stable endpoints
# ---------------------------------------------------------------------------


@app.put("/api/credentials/{provider}/{connection_id}")
async def upsert_credential(
    provider: str,
    connection_id: str,
    request: CredentialUpsertRequest,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> JSONResponse:
    """Create or update one tenant-scoped credential connection."""

    request_id = str(uuid.uuid4())
    tenant_id, _, err = _resolve_tenant_access(
        request_id=request_id,
        tenant_id=x_tenant_id,
        x_user_id=x_user_id,
        authorization=authorization,
    )
    if err is not None:
        return err

    try:
        record = credentials_service.upsert_connection(
            tenant_id=tenant_id,
            provider=provider,
            connection_id=connection_id,
            payload=request.payload,
            name=request.name,
        )
    except Exception as exc:
        return _credentials_error_response(request_id, exc)

    return JSONResponse(
        status_code=200,
        content={"connection": _connection_payload(record)},
        headers={"X-Request-Id": request_id},
    )


@app.get("/api/credentials")
async def list_credentials(
    status: ConnectionStatus | None = None,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> JSONResponse:
    """List connections for one tenant."""

    request_id = str(uuid.uuid4())
    tenant_id, _, err = _resolve_tenant_access(
        request_id=request_id,
        tenant_id=x_tenant_id,
        x_user_id=x_user_id,
        authorization=authorization,
    )
    if err is not None:
        return err

    try:
        records = credentials_service.list_connections(tenant_id=tenant_id, status=status)
    except Exception as exc:
        return _credentials_error_response(request_id, exc)

    return JSONResponse(
        status_code=200,
        content={
            "count": len(records),
            "connections": [_connection_payload(record) for record in records],
        },
        headers={"X-Request-Id": request_id},
    )


@app.get("/api/credentials/{connection_id}")
async def get_credential(
    connection_id: str,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> JSONResponse:
    """Get one tenant-scoped connection by id."""

    request_id = str(uuid.uuid4())
    tenant_id, _, err = _resolve_tenant_access(
        request_id=request_id,
        tenant_id=x_tenant_id,
        x_user_id=x_user_id,
        authorization=authorization,
    )
    if err is not None:
        return err

    try:
        record = credentials_service.get_connection(
            tenant_id=tenant_id, connection_id=connection_id
        )
    except Exception as exc:
        return _credentials_error_response(request_id, exc)

    return JSONResponse(
        status_code=200,
        content={"connection": _connection_payload(record)},
        headers={"X-Request-Id": request_id},
    )


@app.patch("/api/credentials/{connection_id}/status")
async def patch_credential_status(
    connection_id: str,
    request: CredentialStatusPatchRequest,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> JSONResponse:
    """Update one tenant-scoped connection status."""

    request_id = str(uuid.uuid4())
    tenant_id, _, err = _resolve_tenant_access(
        request_id=request_id,
        tenant_id=x_tenant_id,
        x_user_id=x_user_id,
        authorization=authorization,
    )
    if err is not None:
        return err

    try:
        record = credentials_service.update_connection_status(
            tenant_id=tenant_id,
            connection_id=connection_id,
            status=request.status,
        )
    except Exception as exc:
        return _credentials_error_response(request_id, exc)

    return JSONResponse(
        status_code=200,
        content={"connection": _connection_payload(record)},
        headers={"X-Request-Id": request_id},
    )


@app.post("/api/run")
async def run_ingestion(
    request: RunRequest,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> JSONResponse:
    """Run the deterministic ingestion pipeline for a single manifest.

    Status codes
    ------------
    * ``200`` — pipeline completed (status ``OK`` or ``WARN``). The body is
      the frontend-ready shape produced by ``format_response``.
    * ``400`` — the request did not pass ``request_validator`` (missing or
      malformed params/fields). Body: ``{error, request_id, node, reason, details}``.
    * ``502`` — the connector itself failed (network error, upstream API
      down, partial-but-flagged-as-error). Body: same envelope.
    * ``500`` — unexpected pipeline error (e.g. DDL generation failed,
      runtime exception inside a node). Body: same envelope.

    Every response carries an ``X-Request-Id`` header (uuid4) for tracing.
    """
    request_id = str(uuid.uuid4())
    tenant_id, _, err = _resolve_tenant_access(
        request_id=request_id,
        tenant_id=x_tenant_id,
        x_user_id=x_user_id,
        authorization=authorization,
    )
    if err is not None:
        return err

    manifest = get_default_catalog().get(request.manifest_id)
    if manifest is None:
        return _error_response(
            request_id=request_id,
            status_code=400,
            error_key="validation_failed",
            node="request_validator",
            reason=f"unknown manifest_id '{request.manifest_id}'",
            details=["manifest_id not found in catalog"],
        )

    try:
        tenant_ctx = resolve_for_run(
            tenant_id=tenant_id,
            connection_id=request.connection_id,
            expected_platform=str(manifest.get("platform", "")),
        )
    except Exception as exc:
        return _credentials_error_response(request_id, exc)

    initial_state: dict[str, Any] = {
        "manifest_id": request.manifest_id,
        "params": request.params,
        "tenant_id": tenant_id,
        "connection_id": request.connection_id,
        "resolved_tenant": {
            "tenant_id": tenant_ctx.tenant_id,
            "gcp_project": tenant_ctx.gcp_project,
            "service_account": tenant_ctx.service_account,
            "context": tenant_ctx.context,
        },
        "node_results": [],
        "obs_usages": [],
    }

    try:
        # ``build_graph`` is cheap (no I/O, no compilation cache mutation) so
        # constructing per-request keeps tests deterministic and avoids a
        # global stateful instance. A single compiled instance can be wired
        # later if profiling demands it.
        graph = build_graph()
        final = await graph.ainvoke(initial_state)
    except Exception as exc:
        return _error_response(
            request_id=request_id,
            status_code=500,
            error_key="internal",
            reason=str(exc) or exc.__class__.__name__,
        )

    last_status = final.get("last_status")
    node_results = final.get("node_results") or []

    if last_status == "ERR":
        last = node_results[-1] if node_results else None
        if last is None:
            return _error_response(
                request_id=request_id,
                status_code=500,
                error_key="pipeline_failed",
                reason=final.get("final_error") or "no node results recorded",
            )
        node_id = str(last.get("node", "") or "")
        status_code, error_key = _ERR_NODE_TO_HTTP.get(
            node_id, (500, "pipeline_failed")
        )
        return _error_response(
            request_id=request_id,
            status_code=status_code,
            error_key=error_key,
            node=node_id or None,
            reason=str(last.get("reason") or final.get("final_error") or ""),
            details=[str(e) for e in (last.get("errors") or [])],
        )

    formatted = final.get("formatted_response")
    if formatted is None:
        return _error_response(
            request_id=request_id,
            status_code=500,
            error_key="no_formatted_response",
            reason="graph terminated without producing formatted_response",
        )

    return JSONResponse(
        status_code=200,
        content=formatted,
        headers={"X-Request-Id": request_id},
    )


@app.get("/api/oauth/{provider}/authorize")
async def oauth_authorize(
    provider: str,
    connection_id: str = Query(..., min_length=1),
    name: str | None = Query(default=None),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> Response:
    """Start OAuth authorization-code flow for one provider."""

    request_id = str(uuid.uuid4())
    tenant_id, user_id, err = _resolve_tenant_access(
        request_id=request_id,
        tenant_id=x_tenant_id,
        x_user_id=x_user_id,
        authorization=authorization,
    )
    if err is not None:
        return err

    try:
        authorize_url = oauth_service.build_authorize_url(
            provider=provider,
            tenant_id=tenant_id,
            user_id=user_id,
            connection_id=connection_id,
            name=name,
        )
    except Exception as exc:
        return _oauth_error_response(request_id, exc)

    return RedirectResponse(url=authorize_url, status_code=302)


@app.get("/api/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str = Query(..., min_length=1),
    state: str = Query(..., min_length=1),
) -> Response:
    """Finalize OAuth callback by exchanging code and upserting credentials."""

    request_id = str(uuid.uuid4())
    try:
        record = await oauth_service.handle_callback(
            provider=provider,
            code=code,
            state=state,
        )
        success_url = oauth_service.build_success_redirect_url(
            provider=provider,
            connection_id=record.connection_id,
        )
    except Exception as exc:
        return _oauth_error_response(request_id, exc)
    return RedirectResponse(url=success_url, status_code=302)


@app.get("/api/catalog")
async def list_catalog() -> dict[str, Any]:
    """List every connector manifest available in the connectors-library submodule.

    Stable response shape (the contract shared with the frontend; bump
    ``CATALOG_API_VERSION`` if it changes in a non-additive way):

        {
          "version": "1.0",
          "count": <int>,
          "connectors": [
            {
              "id": "meta_facebook_ad_insights",
              "name": "Facebook Ads — Ad-level Insights",
              "platform": "meta",
              "connector": "facebook",
              "version": "0.1.0",
              "status": "alpha" | "beta" | "stable" | "deprecated",
              "description": "..."?,
              "owner": "..."?,
              "available_fields_count": <int>,
              "params_summary": {
                "required": [<param_name>, ...],
                "optional": [<param_name>, ...],
                "one_of": [[<param_name>, ...], ...]
              }
            },
            ...
          ]
        }

    The full manifest (including ``available_fields`` definitions, ``auth``
    contract, ``endpoint`` and ``table_naming``) is served by
    ``GET /api/catalog/{id}`` to keep the index payload small.
    """
    try:
        items = get_default_catalog().list_summaries()
    except ManifestValidationError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"invalid manifest in connectors-library: {exc}",
        ) from exc
    return {"version": CATALOG_API_VERSION, "count": len(items), "connectors": items}


@app.get("/api/catalog/{manifest_id}")
async def get_catalog_entry(manifest_id: str) -> dict[str, Any]:
    """Return the full validated manifest for a single connector by id (snake_case).

    The body is the raw manifest as defined by ``src/ingestion/manifest/schema.json``.
    Returns 404 if no manifest with that id exists in the loaded catalog.
    """
    try:
        manifest = get_default_catalog().get(manifest_id)
    except ManifestValidationError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"invalid manifest in connectors-library: {exc}",
        ) from exc
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"manifest '{manifest_id}' not found")
    return manifest
