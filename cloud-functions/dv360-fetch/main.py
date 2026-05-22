"""dv360-fetch — Cloud Function (gen2) HTTP handler for the DV360 Reports connector.

This is the **MDS-style** deployment of the DV360 Bid Manager Reports
connector. It is the counterpart of :class:`ingestion.dispatcher.http.HTTPBackend`
on the MDS backend side.

Contract
========

Request body (HTTP POST, ``Content-Type: application/json``):

.. code-block:: json

    {
        "tenant_id":        "acme",
        "manifest_id":      "dv360_reports",
        "manifest_version": "0.1.0",
        "fields":           ["Impressions", "Clicks"],   // optional, top-level
        "target_table":     "bronze.dv360_reports",      // optional, top-level
        "params": {
            "data_range":        "LAST_7_DAYS",
            "customStartDate":   "YYYYMMDD",
            "customEndDate":     "YYYYMMDD",
            "poll_timeout_sec":  400,
            "poll_interval_sec": 10
        }
    }

Note that **the payload never contains credentials**. The MDS backend
(``HTTPBackend._scrub_secret_keys``) actively strips any key that smells
like a credential so a bug or a misconfigured manifest cannot leak
tenant material onto the wire. This CF is the only component that
reads the DV360 secrets — it does so from Secret Manager using its
own service account identity (``mds-cf-runner``).

Response body (always JSON):

.. code-block:: json

    {
        "status":  "OK" | "ERR",
        "code":    "FETCH_OK" | "<error_token>",
        "records": [{...}, ...],          // capped preview if very large; full data is in BQ
        "meta":    {... query_id, report_id, bq_table_id, rows_written ...},
        "errors":  []
    }

HTTP status: 200 on ``status="OK"``, 4xx for caller-fault tokens, 5xx
for upstream/internal errors. The body is **always** JSON so the
HTTPBackend's structured-error path keeps working.

Secret resolution
=================

Two secrets per tenant, named after the manifest's
``auth.secrets[].secret_id`` template with ``<client_id>`` replaced
by the request's ``tenant_id``:

* ``client_<tenant_id>_dv360_query_id``            -> single string (DV360 query id)
* ``client_<tenant_id>_dv360_service_account_json`` -> full SA JSON blob

Both secrets live in the **CF's own GCP project** (``GCP_PROJECT``
env var, injected by Cloud Functions). The runtime SA (``mds-cf-runner``)
must hold ``roles/secretmanager.secretAccessor`` on both secrets.

BigQuery write
==============

When ``target_table`` is supplied and the connector returns OK with
records, the CF:

1. Resolves the table id (``dataset.table`` -> ``{GCP_PROJECT}.dataset.table``;
   ``project.dataset.table`` is taken verbatim).
2. Derives a BQ schema by intersecting the first record's keys with the
   bundled manifest's ``available_fields`` (defaulting to ``STRING`` for
   any column the manifest doesn't declare — defensive, since DV360 can
   add columns over time).
3. Calls ``create_table`` with ``exists_ok=True``.
4. Streams rows via ``load_table_from_json`` (atomic, append-only).

If the writes fail, the CF still returns ``status="ERR"`` with
``code="BQ_WRITE_FAILED"`` so the backend trace shows the BQ side
failed (not the connector).

Local development
=================

Use functions-framework against the staged dir produced by
``deploy.sh stage`` (which vendors the connector + manifest into this
directory)::

    functions-framework --source=cloud-functions/dv360-fetch/main.py --target=run --port=8080

Then set ``MDS_CF_BASE_URL=http://localhost:8080`` and
``MDS_RUNTIME=http`` on the backend. Loopback hosts skip the id_token
check on the client side, so no real Google credentials are needed for
the round-trip plumbing test — only the SM/BQ paths require ADC.
"""

from __future__ import annotations

import json
import logging
import os
import traceback
from pathlib import Path
from typing import Any

import functions_framework

# Lazy GCP imports below — keep top-level imports cheap so unit tests
# can run on a vanilla Python install without the GCP SDKs.

LOGGER = logging.getLogger("dv360-fetch")
LOGGER.setLevel(logging.INFO)

# The manifest is the SSoT for connector identity, available fields, and
# secret naming. It is bundled into the deployment by deploy.sh so the
# CF can read it at startup without reaching out to anything.
MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"

# Cap on how many records to echo in the HTTP response when BQ write
# succeeded — the source of truth for the rows is BQ in that case, and
# echoing a million rows would blow up the gen2 response size limit
# (32 MiB) and the backend's logs. We cap at 200 so the trace still
# shows enough to eyeball.
RECORDS_PREVIEW_CAP = 200

# Default BQ types when a column from the report doesn't appear in the
# manifest. STRING is the universally-loadable type — never picks the
# wrong thing.
DEFAULT_BQ_TYPE = "STRING"


# ---------------------------------------------------------------------------
# Manifest cache (loaded once per CF cold start)
# ---------------------------------------------------------------------------

def _load_manifest() -> dict[str, Any]:
    """Read the bundled manifest.json. Returns ``{}`` on any error.

    A missing or invalid manifest is logged but does not crash the CF —
    we degrade to "all columns are STRING" rather than 5xx'ing every
    request. The deploy script is responsible for staging a valid
    manifest, and the test suite asserts on that.
    """
    try:
        with MANIFEST_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        LOGGER.warning("manifest.json not found at %s — schema fallback", MANIFEST_PATH)
        return {}
    except json.JSONDecodeError as exc:
        LOGGER.error("manifest.json malformed (%s) — schema fallback", exc)
        return {}


_MANIFEST_CACHE: dict[str, Any] | None = None


def _manifest() -> dict[str, Any]:
    """Memoised access to the bundled manifest."""
    global _MANIFEST_CACHE
    if _MANIFEST_CACHE is None:
        _MANIFEST_CACHE = _load_manifest()
    return _MANIFEST_CACHE


def _expected_manifest_id() -> str:
    """ID this CF is supposed to handle (per the bundled manifest)."""
    return (_manifest().get("id") or "dv360_reports")


# ---------------------------------------------------------------------------
# Secret Manager
# ---------------------------------------------------------------------------

def _gcp_project() -> str:
    """Return the GCP project the CF is running in.

    Cloud Functions gen2 injects this as ``GCP_PROJECT`` (legacy) or
    ``GOOGLE_CLOUD_PROJECT`` (newer). Either is fine; we accept both.
    """
    proj = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not proj:
        raise RuntimeError(
            "GCP_PROJECT / GOOGLE_CLOUD_PROJECT env var is not set — "
            "the CF cannot resolve secrets without knowing its project."
        )
    return proj


def _resolve_secret(secret_id: str, version: str = "latest") -> str:
    """Read a Secret Manager secret payload as UTF-8 text.

    Lazy import of google-cloud-secret-manager so unit tests don't have
    to install it. Tests stub this function directly.
    """
    from google.cloud import secretmanager  # type: ignore

    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{_gcp_project()}/secrets/{secret_id}/versions/{version}"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")


def _build_connector_context(tenant_id: str) -> dict[str, Any]:
    """Pull the two DV360 secrets for ``tenant_id`` and return a connector context.

    Returns:
        dict suitable for passing to ``dv360_reports.fetch`` as
        ``context``: ``{"query_id": ..., "service_account_json": ...}``.

    Raises:
        :class:`RuntimeError` if either secret is missing — the caller
        translates that into an ERR response with code
        ``MISSING_SECRET``.
    """
    base = f"client_{tenant_id}_dv360"
    query_id_secret = f"{base}_query_id"
    sa_json_secret = f"{base}_service_account_json"

    try:
        query_id = _resolve_secret(query_id_secret).strip()
    except Exception as exc:  # noqa: BLE001 — wrap-and-tag
        raise RuntimeError(
            f"could not read secret '{query_id_secret}': {type(exc).__name__}: {exc}"
        ) from exc

    try:
        sa_json = _resolve_secret(sa_json_secret)
    except Exception as exc:  # noqa: BLE001 — wrap-and-tag
        raise RuntimeError(
            f"could not read secret '{sa_json_secret}': {type(exc).__name__}: {exc}"
        ) from exc

    return {
        "query_id": query_id,
        "service_account_json": sa_json,
    }


# ---------------------------------------------------------------------------
# BigQuery write
# ---------------------------------------------------------------------------

def _resolve_table_id(target_table: str) -> str:
    """Return a fully-qualified BigQuery table id.

    Accepts:
      * ``dataset.table``                  -> ``{project}.dataset.table``
      * ``project.dataset.table``          -> verbatim
      * anything else                      -> raises ``ValueError``
    """
    if not target_table or not isinstance(target_table, str):
        raise ValueError(f"target_table must be a non-empty string, got {target_table!r}")
    parts = target_table.split(".")
    if len(parts) == 2:
        return f"{_gcp_project()}.{parts[0]}.{parts[1]}"
    if len(parts) == 3:
        return target_table
    raise ValueError(
        f"target_table must be 'dataset.table' or 'project.dataset.table', got {target_table!r}"
    )


def _field_type_lookup() -> dict[str, str]:
    """Lower-cased {name: bq_type} from the bundled manifest's available_fields."""
    out: dict[str, str] = {}
    for field in _manifest().get("available_fields") or []:
        name = field.get("name")
        bq_type = field.get("type", DEFAULT_BQ_TYPE)
        if isinstance(name, str) and name:
            out[name.lower()] = bq_type
    return out


def _derive_bq_schema(records: list[dict]) -> list[dict[str, str]]:
    """Derive a BigQuery schema (list of ``{name, type}`` dicts) from the records.

    Strategy: use the first record's keys as the column set, look up
    types in the manifest, default to STRING for unknown columns. This
    is intentionally permissive — DV360 occasionally adds new fields
    server-side and we don't want a deploy block-out just because we
    haven't updated the manifest yet.
    """
    if not records:
        return []
    lookup = _field_type_lookup()
    schema: list[dict[str, str]] = []
    for col in records[0].keys():
        bq_type = lookup.get(str(col).lower(), DEFAULT_BQ_TYPE)
        # NULLABLE mode is the BQ default; we never want REQUIRED here
        # because DV360 can emit empty cells for any column.
        schema.append({"name": col, "type": bq_type, "mode": "NULLABLE"})
    return schema


def _write_records_to_bq(
    *,
    table_id: str,
    records: list[dict],
) -> dict[str, Any]:
    """Append ``records`` to ``table_id``, creating the table if needed.

    Returns metadata: ``{"bq_table_id", "rows_written", "schema_created"}``.

    Lazy-imports google-cloud-bigquery so unit tests don't depend on it.
    """
    from google.cloud import bigquery  # type: ignore

    client = bigquery.Client(project=_gcp_project())

    schema_raw = _derive_bq_schema(records)
    bq_schema = [
        bigquery.SchemaField(f["name"], f["type"], mode=f["mode"]) for f in schema_raw
    ]

    # Create the table on first write. We don't ALTER existing tables —
    # if a column appears that wasn't in the original schema, the
    # load_table_from_json call below will surface a clear error.
    schema_created = False
    try:
        client.get_table(table_id)
    except Exception:  # noqa: BLE001 — NotFound is the expected branch
        table_ref = bigquery.Table(table_id, schema=bq_schema)
        client.create_table(table_ref, exists_ok=True)
        schema_created = True
        LOGGER.info("Created BQ table %s with %d columns", table_id, len(bq_schema))

    job_config = bigquery.LoadJobConfig(
        schema=bq_schema,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        # Tolerate the connector adding new columns over time; the
        # operator can ALTER the table separately to keep them.
        schema_update_options=[
            bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION,
        ],
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
    )
    job = client.load_table_from_json(records, table_id, job_config=job_config)
    job.result()  # blocks until load done; raises on failure

    return {
        "bq_table_id": table_id,
        "rows_written": len(records),
        "schema_created": schema_created,
    }


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _err(
    *,
    code: str,
    message: str,
    http_status: int,
    meta: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], int]:
    return (
        {
            "status": "ERR",
            "code": code,
            "records": [],
            "meta": meta or {},
            "errors": [message],
        },
        http_status,
    )


def _truncated_preview(records: list[dict]) -> list[dict]:
    """Return at most ``RECORDS_PREVIEW_CAP`` records for the HTTP response."""
    if len(records) <= RECORDS_PREVIEW_CAP:
        return records
    return records[:RECORDS_PREVIEW_CAP]


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

@functions_framework.http
def run(request):  # noqa: C901 — handler is a sequence of guards; splitting hurts readability
    """HTTP entrypoint for the dv360-fetch Cloud Function."""
    # ---- 0. Parse body ----
    try:
        body = request.get_json(silent=True) or {}
    except Exception as exc:  # noqa: BLE001
        return _err(
            code="INVALID_BODY",
            message=f"could not parse request body as JSON: {exc}",
            http_status=400,
        )

    tenant_id = body.get("tenant_id")
    manifest_id = body.get("manifest_id")
    params = body.get("params") or {}
    fields = body.get("fields")           # top-level, lifted by HTTPBackend
    target_table = body.get("target_table")

    # ---- 1. Validate required fields ----
    if not tenant_id or not isinstance(tenant_id, str):
        return _err(
            code="MISSING_TENANT_ID",
            message="body.tenant_id is required and must be a string.",
            http_status=400,
        )
    if not manifest_id or not isinstance(manifest_id, str):
        return _err(
            code="MISSING_MANIFEST_ID",
            message="body.manifest_id is required and must be a string.",
            http_status=400,
        )
    expected = _expected_manifest_id()
    if manifest_id != expected:
        return _err(
            code="MANIFEST_MISMATCH",
            message=(
                f"this CF only handles manifest_id={expected!r}, "
                f"got {manifest_id!r}. Wrong CF URL?"
            ),
            http_status=400,
        )
    if not isinstance(params, dict):
        return _err(
            code="INVALID_PARAMS",
            message=f"body.params must be an object, got {type(params).__name__}.",
            http_status=400,
        )

    # Reunite ``fields`` with ``params`` for the connector (the
    # connector reads it from params; HTTPBackend lifted it to the top
    # of the payload). We do NOT mutate the caller's dict.
    if fields is not None:
        params = {**params, "fields": fields}

    # ---- 2. Resolve secrets from SM (CF's own SA identity) ----
    try:
        connector_context = _build_connector_context(tenant_id)
    except RuntimeError as exc:
        return _err(
            code="MISSING_SECRET",
            message=str(exc),
            http_status=500,
            meta={"tenant_id": tenant_id, "manifest_id": manifest_id},
        )

    # ---- 3. Call the connector ----
    try:
        # Lazy-import so cold-start cost is paid once per CF instance,
        # and so unit tests can monkeypatch the symbol freely.
        from dv360_reports import fetch as dv360_fetch
    except ImportError as exc:
        return _err(
            code="CONNECTOR_NOT_PACKAGED",
            message=(
                f"could not import dv360_reports: {exc}. The deploy script "
                f"must vendor connectors-library/dv360/reports/*.py into the CF dir."
            ),
            http_status=500,
        )

    try:
        result = dv360_fetch(params=params, context=connector_context)
    except Exception as exc:  # noqa: BLE001 — connector raised something unexpected
        LOGGER.error("dv360 fetch raised: %s\n%s", exc, traceback.format_exc())
        return _err(
            code="CONNECTOR_RAISED",
            message=f"{type(exc).__name__}: {exc}",
            http_status=500,
            meta={"tenant_id": tenant_id, "manifest_id": manifest_id},
        )

    # The connector returns a dict in the contract shape:
    #   {status, code, records, meta, errors}
    # We layer in BQ write metadata + cap the record preview, then pass
    # it back. Don't mutate the connector's dict — return a new one.
    status = str(result.get("status", "ERR"))
    code = result.get("code", "UNKNOWN")
    records = result.get("records") or []
    meta = dict(result.get("meta") or {})
    errors = list(result.get("errors") or [])

    if status != "OK":
        # Pass connector errors through; HTTP 200 vs 5xx depends on the
        # code. Auth/forbidden are caller-visible so 401/403; others 500.
        http_status = {
            "UNAUTHORIZED": 401,
            "INVALID_CREDENTIALS": 401,
            "MISSING_CREDENTIALS": 401,
            "FORBIDDEN": 403,
            "MISSING_QUERY_ID": 400,
            "INVALID_PARAMS": 400,
            "POLL_TIMEOUT": 504,
        }.get(str(code), 500)
        return (
            {
                "status": status,
                "code": code,
                "records": records if isinstance(records, list) else [],
                "meta": meta,
                "errors": errors,
            },
            http_status,
        )

    # ---- 4. BQ write (only when target_table provided + records present) ----
    bq_meta: dict[str, Any] = {}
    if target_table and isinstance(records, list) and records:
        try:
            table_id = _resolve_table_id(target_table)
        except ValueError as exc:
            return _err(
                code="INVALID_TARGET_TABLE",
                message=str(exc),
                http_status=400,
                meta={"tenant_id": tenant_id, "target_table": target_table},
            )
        try:
            bq_meta = _write_records_to_bq(table_id=table_id, records=records)
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("BQ write failed: %s\n%s", exc, traceback.format_exc())
            return _err(
                code="BQ_WRITE_FAILED",
                message=f"{type(exc).__name__}: {exc}",
                http_status=500,
                meta={
                    "tenant_id": tenant_id,
                    "target_table": target_table,
                    "table_id_resolved": table_id,
                    "records_returned_by_connector": len(records),
                    **meta,
                },
            )

    # ---- 5. Success response ----
    merged_meta: dict[str, Any] = {
        **meta,
        **bq_meta,
        "tenant_id": tenant_id,
        "manifest_id": manifest_id,
        "records_total": len(records) if isinstance(records, list) else None,
    }
    preview = _truncated_preview(records) if isinstance(records, list) else records
    if isinstance(records, list) and len(records) > RECORDS_PREVIEW_CAP:
        merged_meta["records_preview_capped_at"] = RECORDS_PREVIEW_CAP

    return (
        {
            "status": "OK",
            "code": code,
            "records": preview,
            "meta": merged_meta,
            "errors": errors,
        },
        200,
    )


__all__ = ["run"]
