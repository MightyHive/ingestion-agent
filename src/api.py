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

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

# Load .env from the repo root before any other imports that read env vars.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from credentials import init_db
from credentials import service as credentials_service
from credentials.exceptions import (
    ConnectionInactiveError,
    ConnectionNotFoundError,
    InvalidStatusTransitionError,
    SecretManagerError,
    SecretPayloadError,
)
from credentials.schemas import ConnectionRecord, ConnectionStatus
from ingestion import build_graph
from ingestion.manifest import (
    CATALOG_API_VERSION,
    ManifestValidationError,
    get_default_catalog,
)


@asynccontextmanager
async def _lifespan(app: FastAPI):
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

    The optional ``tenant_id`` selects which row of ``~/.mds/tenants.json``
    is loaded by ``TenantContext.resolve``. When omitted, we fall back to
    ``_DEFAULT_TENANT_ID`` (``"dev"``) so the existing Phase 3/4 smoke
    flows keep working without a frontend change. Once Mili surfaces a
    tenant selector, the frontend should always pass it explicitly.

    ``params.target_table`` is an optional override for the destination
    BigQuery table. When omitted, ``data_architect`` substitutes the
    manifest's ``table_naming.bronze_pattern`` — including the new
    ``{tenant_id}`` token — so the default becomes
    ``bronze.<connector>_<tenant_id>`` and the frontend can show it
    before the user submits.
    """

    manifest_id: str = Field(
        ...,
        min_length=1,
        description="Globally unique manifest id as exposed by GET /api/catalog.",
    )
    tenant_id: str | None = Field(
        default=None,
        description=(
            "Tenant key that selects the row of ~/.mds/tenants.json to use. "
            "When None, the backend falls back to its default tenant (currently 'dev'). "
            "Also used to substitute the {tenant_id} token in bronze_pattern."
        ),
    )
    connection_id: str | None = Field(
        default=None,
        description=(
            "ID of the credentials connection to use. When provided, the Cloud "
            "Function reads a single JSON secret named {tenant}-{provider}-{connection_id} "
            "from Secret Manager. When omitted, the CF falls back to the legacy "
            "two-secret format (client_{tenant}_{provider}_{field})."
        ),
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Connector parameters. Must include 'fields' (list of selectable "
            "available_fields names; empty list means 'all selectable'). "
            "May also include 'target_table' to override the default BQ destination. "
            "Other keys must match the manifest's params schema."
        ),
    )


class CredentialUpsertRequest(BaseModel):
    payload: dict[str, Any] | str = Field(
        ...,
        description="Secret payload (token string or JSON object).",
    )
    name: str | None = Field(default=None)


class CredentialStatusPatchRequest(BaseModel):
    status: ConnectionStatus


# ---------------------------------------------------------------------------
# Error helpers
# ---------------------------------------------------------------------------

# Hardcoded tenant for Phase 3/4. Phase 5 replaces this with a real resolver
# (header ``X-Tenant-Id`` + Secret Manager + SA impersonation).
_DEFAULT_TENANT_ID = "dev"

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


def _connection_payload(record: ConnectionRecord) -> dict[str, Any]:
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
    if isinstance(exc, SecretPayloadError):
        return _error_response(request_id=request_id, status_code=400, error_key="invalid_payload", reason=str(exc))
    if isinstance(exc, ConnectionNotFoundError):
        return _error_response(request_id=request_id, status_code=404, error_key="connection_not_found", reason=str(exc))
    if isinstance(exc, ConnectionInactiveError):
        return _error_response(request_id=request_id, status_code=409, error_key="connection_inactive", reason=str(exc))
    if isinstance(exc, InvalidStatusTransitionError):
        return _error_response(request_id=request_id, status_code=409, error_key="invalid_status_transition", reason=str(exc))
    if isinstance(exc, SecretManagerError):
        return _error_response(request_id=request_id, status_code=502, error_key="secret_manager_failed", reason=str(exc))
    return _error_response(request_id=request_id, status_code=500, error_key="internal", reason=str(exc) or exc.__class__.__name__)


# ---------------------------------------------------------------------------
# Credentials endpoints
# ---------------------------------------------------------------------------


@app.put("/api/credentials/{provider}/{connection_id}")
async def upsert_credential(
    provider: str,
    connection_id: str,
    request: CredentialUpsertRequest,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> JSONResponse:
    request_id = str(uuid.uuid4())
    tenant_id = (x_tenant_id or "").strip() or _DEFAULT_TENANT_ID
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
) -> JSONResponse:
    request_id = str(uuid.uuid4())
    tenant_id = (x_tenant_id or "").strip() or _DEFAULT_TENANT_ID
    try:
        records = credentials_service.list_connections(tenant_id=tenant_id, status=status)
    except Exception as exc:
        return _credentials_error_response(request_id, exc)
    return JSONResponse(
        status_code=200,
        content={"count": len(records), "connections": [_connection_payload(r) for r in records]},
        headers={"X-Request-Id": request_id},
    )


@app.get("/api/credentials/{connection_id}")
async def get_credential(
    connection_id: str,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> JSONResponse:
    request_id = str(uuid.uuid4())
    tenant_id = (x_tenant_id or "").strip() or _DEFAULT_TENANT_ID
    try:
        record = credentials_service.get_connection(tenant_id=tenant_id, connection_id=connection_id)
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
) -> JSONResponse:
    request_id = str(uuid.uuid4())
    tenant_id = (x_tenant_id or "").strip() or _DEFAULT_TENANT_ID
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


# ---------------------------------------------------------------------------
# Ingestion endpoint
# ---------------------------------------------------------------------------


@app.post("/api/run")
async def run_ingestion(request: RunRequest) -> JSONResponse:
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

    # Tenant resolution: request body wins; otherwise we use the default
    # (Phase 3/4 carry-over). A blank string from the frontend is treated
    # as "not provided" so an empty input field doesn't crash the graph.
    tenant_id = (request.tenant_id or "").strip() or _DEFAULT_TENANT_ID

    initial_state: dict[str, Any] = {
        "manifest_id": request.manifest_id,
        "params": request.params,
        "tenant_id": tenant_id,
        "connection_id": (request.connection_id or "").strip() or None,
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
