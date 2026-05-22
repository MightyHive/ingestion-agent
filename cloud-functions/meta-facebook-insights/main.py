"""meta-facebook-insights — Cloud Function (gen2) HTTP handler for the
Meta (Facebook) Ad-Insights connector.

This is the **MDS-style** deployment of the
``connectors-library/meta/facebook/facebook_ads.py`` connector. It is
the counterpart of :class:`ingestion.dispatcher.http.HTTPBackend` on
the MDS backend side and follows the same pattern as ``dv360-fetch``:
one Cloud Function per manifest.

Contract
========

Request body (HTTP POST, ``Content-Type: application/json``):

.. code-block:: json

    {
        "tenant_id":        "cliente1",
        "manifest_id":      "meta_facebook_ad_insights",
        "manifest_version": "0.1.0",
        "fields":           ["impressions", "clicks", "spend"],  // optional, top-level
        "target_table":     "bronze.meta_facebook_ad_insights",   // optional, top-level
        "params": {
            "days_back":  14,
            "date_start": "2026-05-01",
            "date_stop":  "2026-05-20"
        }
    }

Note that **the payload never contains credentials**. The MDS backend
(``HTTPBackend._scrub_secret_keys``) actively strips any key that smells
like a credential so a bug or misconfigured manifest cannot leak tenant
material onto the wire. This CF is the only component that reads the
Meta secrets — it does so from Secret Manager using its own service
account identity (``mds-cf-runner``).

Response body (always JSON):

.. code-block:: json

    {
        "status":  "OK" | "ERR",
        "code":    "FETCH_OK" | "<error_token>",
        "records": [{...}, ...],   // the manifest's metadata.response_subkey level, capped preview
        "meta":    {... bq_table_id, rows_written, total_campaigns, total_adsets, total_ads ...},
        "errors":  []
    }

HTTP status: 200 on ``status="OK"``, 4xx for caller-fault tokens, 5xx
for upstream/internal errors. The body is **always** JSON so the
HTTPBackend's structured-error path keeps working.

Secret resolution
=================

Two secrets per tenant, following the project-wide naming convention:

* ``client_<tenant_id>_meta_access_token``   -> Meta System User Token (string)
* ``client_<tenant_id>_meta_ad_account_id``  -> Ad account id (e.g. ``act_1234567890``)

Both secrets live in the **CF's own GCP project** (``GCP_PROJECT`` env
var, injected by Cloud Functions). The runtime SA (``mds-cf-runner``)
must hold ``roles/secretmanager.secretAccessor`` on both secrets.

Records subkey
==============

The Meta connector returns ``records`` as a **dict** with three keys:
``campaigns``, ``adsets``, ``ads``. The CF reads
``manifest.metadata.response_subkey`` (default ``"ads"``) and writes
only that level to BigQuery. The HTTP response echoes the same level
(capped to ``RECORDS_PREVIEW_CAP``); the other levels are exposed via
``meta.total_campaigns / total_adsets / total_ads`` for visibility.

BigQuery write
==============

When ``target_table`` is supplied and the selected level has records,
the CF:

1. Resolves the table id (``dataset.table`` -> ``{GCP_PROJECT}.dataset.table``;
   ``project.dataset.table`` is taken verbatim).
2. Derives a BigQuery schema by intersecting the first record's keys
   with the bundled manifest's ``available_fields`` (defaulting to
   ``STRING`` for any column the manifest does not declare).
3. Calls ``create_table`` with ``exists_ok=True``.
4. Streams rows via ``load_table_from_json`` (atomic, append-only).

If the write fails, the CF returns ``status="ERR"`` with
``code="BQ_WRITE_FAILED"`` so the backend trace shows the BQ side
failed (not the connector).

Local development
=================

Use functions-framework against the staged dir produced by
``deploy.sh stage`` (which vendors the connector + manifest into this
directory)::

    functions-framework --source=cloud-functions/meta-facebook-insights/main.py --target=run --port=8080

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import functions_framework

# Lazy GCP imports below — keep top-level imports cheap so unit tests
# can run on a vanilla Python install without the GCP SDKs.

LOGGER = logging.getLogger("meta-facebook-insights")
LOGGER.setLevel(logging.INFO)

# The manifest is the SSoT for connector identity, available fields,
# response_subkey, and secret naming. It is bundled into the deployment
# by deploy.sh so the CF can read it at startup without reaching out to
# anything.
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

# Fallback response_subkey if the manifest is missing or malformed.
# "ads" matches the current Facebook manifest at v0.1.0.
DEFAULT_RESPONSE_SUBKEY = "ads"

# System-stamped columns added by the CF itself (not by the connector).
# These ALWAYS win in the schema type lookup so a connector cannot
# accidentally redeclare them with the wrong type. The CF guarantees
# they are present as the last column(s) of every record written to BQ.
_SYSTEM_FIELDS: dict[str, str] = {
    "ingested_at": "TIMESTAMP",
}


# ---------------------------------------------------------------------------
# Manifest cache (loaded once per CF cold start)
# ---------------------------------------------------------------------------

def _load_manifest() -> dict[str, Any]:
    """Read the bundled manifest.json. Returns ``{}`` on any error.

    A missing or invalid manifest is logged but does not crash the CF —
    we degrade to STRING-everything + default subkey rather than 5xx'ing
    every request. The deploy script is responsible for staging a valid
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
    return (_manifest().get("id") or "meta_facebook_ad_insights")


def _response_subkey() -> str:
    """Which level of records.* to write to BQ (default 'ads')."""
    meta = _manifest().get("metadata") or {}
    subkey = meta.get("response_subkey") or DEFAULT_RESPONSE_SUBKEY
    return str(subkey)


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
    """Pull the two Meta secrets for ``tenant_id`` and return a connector context.

    Returns:
        dict suitable for passing to ``facebook_ads.fetch`` as
        ``context``: ``{"ad_account_id": ..., "access_token": ...}``.

    Raises:
        :class:`RuntimeError` if either secret is missing — the caller
        translates that into an ERR response with code
        ``MISSING_SECRET``.
    """
    base = f"client_{tenant_id}_meta"
    access_token_secret = f"{base}_access_token"
    ad_account_id_secret = f"{base}_ad_account_id"

    try:
        access_token = _resolve_secret(access_token_secret).strip()
    except Exception as exc:  # noqa: BLE001 — wrap-and-tag
        raise RuntimeError(
            f"could not read secret '{access_token_secret}': {type(exc).__name__}: {exc}"
        ) from exc

    try:
        ad_account_id = _resolve_secret(ad_account_id_secret).strip()
    except Exception as exc:  # noqa: BLE001 — wrap-and-tag
        raise RuntimeError(
            f"could not read secret '{ad_account_id_secret}': {type(exc).__name__}: {exc}"
        ) from exc

    return {
        "ad_account_id": ad_account_id,
        "access_token": access_token,
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
    """Lower-cased {name: bq_type} from the bundled manifest's available_fields.

    System fields (see ``_SYSTEM_FIELDS``) are merged in last so they
    override any conflicting manifest declaration. This guarantees that
    e.g. ``ingested_at`` is always TIMESTAMP regardless of what (if
    anything) the connector or manifest says about it.
    """
    out: dict[str, str] = {}
    for field in _manifest().get("available_fields") or []:
        name = field.get("name")
        bq_type = field.get("type", DEFAULT_BQ_TYPE)
        if isinstance(name, str) and name:
            out[name.lower()] = bq_type
    for sys_name, sys_type in _SYSTEM_FIELDS.items():
        out[sys_name.lower()] = sys_type
    return out


def _stamp_ingestion_timestamp(
    records: list[dict], *, now: datetime | None = None
) -> str:
    """Append ``ingested_at`` (UTC ISO TIMESTAMP) to every record in-place.

    A single timestamp is reused for the whole batch — this makes it
    trivial to query "everything from run X" with a single equality
    predicate, and matches the semantics of "the moment we obtained
    this batch from the upstream API". Returns the timestamp string so
    the caller can echo it in the response ``meta`` for traceability.

    The dict assignment puts ``ingested_at`` at the end of each
    record's key order, which (Py3.7+ ordered dicts) makes it the last
    column in the derived BQ schema. The ``now`` kwarg is provided so
    unit tests can pin the value.
    """
    moment = now or datetime.now(timezone.utc)
    # isoformat() with a TZ-aware datetime emits the offset (``+00:00``),
    # which BigQuery TIMESTAMP accepts natively.
    ts = moment.isoformat()
    for record in records:
        # Overwrite if (very unlikely) the connector populated this key:
        # the CF is authoritative for when the data was ingested.
        record["ingested_at"] = ts
    return ts


def _derive_bq_schema(records: list[dict]) -> list[dict[str, str]]:
    """Derive a BigQuery schema (list of ``{name, type}`` dicts) from the records.

    Strategy: use the first record's keys as the column set, look up
    types in the manifest, default to STRING for unknown columns. This
    is intentionally permissive — Meta occasionally adds new fields
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
        # because Meta can emit empty cells for any column.
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

    # Stamp every record with the ingestion timestamp BEFORE the schema
    # is derived so ``ingested_at`` shows up as the final column. We
    # keep the value here to echo it in the response meta for tracing.
    ingested_at = _stamp_ingestion_timestamp(records)

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
        "ingested_at": ingested_at,
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


def _select_level_records(records_dict: Any, subkey: str) -> list[dict]:
    """Extract a single level from the connector's records dict.

    The Meta connector returns ``records`` as
    ``{"campaigns": [...], "adsets": [...], "ads": [...]}``. The CF
    writes only one level to BQ (controlled by
    ``manifest.metadata.response_subkey``). Returns ``[]`` when the
    subkey is missing or the structure is unexpected — the caller logs
    a meta field so this is visible in the trace.
    """
    if not isinstance(records_dict, dict):
        return []
    level = records_dict.get(subkey)
    if not isinstance(level, list):
        return []
    return level


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

@functions_framework.http
def run(request):  # noqa: C901 — handler is a sequence of guards; splitting hurts readability
    """HTTP entrypoint for the meta-facebook-insights Cloud Function."""
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
        from facebook_ads import fetch as meta_fetch
    except ImportError as exc:
        return _err(
            code="CONNECTOR_NOT_PACKAGED",
            message=(
                f"could not import facebook_ads: {exc}. The deploy script "
                f"must vendor connectors-library/meta/facebook/*.py into the CF dir."
            ),
            http_status=500,
        )

    try:
        result = meta_fetch(params=params, context=connector_context)
    except Exception as exc:  # noqa: BLE001 — connector raised something unexpected
        LOGGER.error("meta fetch raised: %s\n%s", exc, traceback.format_exc())
        return _err(
            code="CONNECTOR_RAISED",
            message=f"{type(exc).__name__}: {exc}",
            http_status=500,
            meta={"tenant_id": tenant_id, "manifest_id": manifest_id},
        )

    # The connector returns a dict in the contract shape:
    #   {status, code, records, meta, errors}
    # Where records is a dict {campaigns, adsets, ads}. We pick one
    # level (manifest.metadata.response_subkey) for BQ + preview.
    status = str(result.get("status", "ERR"))
    code = result.get("code", "UNKNOWN")
    records_dict = result.get("records") or {}
    meta = dict(result.get("meta") or {})
    errors = list(result.get("errors") or [])

    if status != "OK":
        # Pass connector errors through; HTTP status depends on the
        # code. Meta-specific mapping:
        #   UNAUTHORIZED / MISSING_CREDENTIALS    -> 401
        #   FORBIDDEN                              -> 403
        #   MISSING_ACCOUNT_ID                     -> 400
        #   UNEXPECTED_ERROR                       -> 500
        http_status = {
            "UNAUTHORIZED": 401,
            "MISSING_CREDENTIALS": 401,
            "FORBIDDEN": 403,
            "MISSING_ACCOUNT_ID": 400,
            "INVALID_PARAMS": 400,
            "UNEXPECTED_ERROR": 500,
        }.get(str(code), 500)
        return (
            {
                "status": status,
                "code": code,
                # Echo whatever level was selected, even on error (usually empty).
                "records": [],
                "meta": meta,
                "errors": errors,
            },
            http_status,
        )

    # ---- 4. Pick the level for BQ + preview ----
    subkey = _response_subkey()
    level_records = _select_level_records(records_dict, subkey)

    # Surface total counts per level for visibility, regardless of which
    # level we write to BQ. The connector populates these in meta already
    # but we re-derive them defensively in case the connector's meta is
    # missing keys.
    if isinstance(records_dict, dict):
        for lvl in ("campaigns", "adsets", "ads"):
            key = f"total_{lvl}"
            if key not in meta:
                lvl_list = records_dict.get(lvl)
                if isinstance(lvl_list, list):
                    meta[key] = len(lvl_list)

    meta["response_subkey"] = subkey

    # ---- 5. BQ write (only when target_table provided + level has records) ----
    bq_meta: dict[str, Any] = {}
    if target_table and level_records:
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
            bq_meta = _write_records_to_bq(table_id=table_id, records=level_records)
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
                    "records_returned_by_connector": len(level_records),
                    **meta,
                },
            )

    # ---- 6. Success response ----
    merged_meta: dict[str, Any] = {
        **meta,
        **bq_meta,
        "tenant_id": tenant_id,
        "manifest_id": manifest_id,
        "records_total": len(level_records),
    }
    preview = _truncated_preview(level_records)
    if len(level_records) > RECORDS_PREVIEW_CAP:
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
