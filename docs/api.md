# MDS API — Contract Reference

> Single source of truth for the HTTP endpoints exposed by the backend. Keep this doc in sync when shape or status codes change.
>
> Companion docs: [`architecture.md`](architecture.md) (system overview) · [`onboarding-local.md`](onboarding-local.md) (run locally) · [`fase5-runbook.md`](fase5-runbook.md) (deploy + smoke).

## Index

1. [Quick reference](#1-quick-reference)
2. [Catalog](#2-catalog) — `GET /api/catalog`, `GET /api/catalog/{id}`
3. [Ingestion](#3-ingestion) — `POST /api/run`
4. [Credentials](#4-credentials) — CRUD over `/api/credentials`
5. [Conventions](#5-conventions) — headers, errors, BigQuery type mapping
6. [Environment variables](#6-environment-variables)
7. [Glossary](#7-glossary)

---

## 1. Quick reference

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/catalog`                                  | List available connectors (manifests) for the picker |
| `GET`  | `/api/catalog/{manifest_id}`                    | Full manifest for one connector |
| `POST` | `/api/run`                                      | Run the deterministic ingestion pipeline (sync) |
| `PUT`  | `/api/credentials/{provider}/{connection_id}`   | Upsert a tenant credential (creates secret + DB row) |
| `GET`  | `/api/credentials`                              | List credentials for a tenant |
| `GET`  | `/api/credentials/{connection_id}`              | Get one credential |
| `PATCH`| `/api/credentials/{connection_id}/status`       | Transition status (`active` ↔ `inactive`, either → `revoked`) |

**Base URL (dev):** `http://localhost:8000`. CORS is open (`allow_origins=["*"]`) for dev and must be closed before any prod deploy.

All responses include `X-Request-Id` (uuid4) for tracing.

---

## 2. Catalog

### `GET /api/catalog`

Lists every manifest discovered in the `connectors-library` submodule.

**Response 200:**

```json
{
  "version": "1.0",
  "count": 2,
  "connectors": [
    {
      "id": "meta_facebook_ad_insights",
      "name": "Facebook Ads — Ad-level Insights",
      "platform": "meta",
      "connector": "facebook",
      "version": "0.1.0",
      "status": "alpha",
      "description": "Daily ad-level performance insights ...",
      "owner": "Ivan Krawchik",
      "available_fields_count": 31,
      "params_summary": {
        "required": ["fields"],
        "optional": ["days_back", "date_start", "date_stop", "since", "until"],
        "one_of":   [["days_back"], ["date_start", "date_stop"], ["since", "until"]]
      }
    }
  ]
}
```

| Field | Notes |
|---|---|
| `id` | Snake_case primary key. Used as path param in `/api/catalog/{id}` and as suffix in BigQuery (Bronze). |
| `status` | `alpha` \| `beta` \| `stable` \| `deprecated`. UI may filter non-stable behind a feature flag. |
| `params_summary.one_of` | Mutually exclusive groups. The validator requires exactly one group fully present. |

Returns `count: 0, connectors: []` when the submodule is not initialized. Returns `500` if any manifest fails schema validation — this is intentional (CI should catch bad manifests).

### `GET /api/catalog/{id}`

Returns the full manifest (same shape as `connectors-library/<platform>/<connector>/manifest.json`, validated against `src/ingestion/manifest/schema.json`).

For UI rendering, the important blocks are:

- `available_fields` — render the column selector. Each item: `{name, type, mode?, description?, items_type?, fields?, selectable?}`. Skip items where `selectable: false`.
- `params` — render the form. Each: `{name, type, default?, minimum?, maximum?, enum?, pattern?, description?}`. Respect `params.one_of`.
- `name`, `description`, `version`, `status` — header of the flow.

Everything else (`endpoint`, `auth`, `table_naming`, `limits`, `metadata`) is backend-only.

**Status codes:** `200` (manifest), `404` (unknown id), `500` (invalid manifests in the submodule).

---

## 3. Ingestion

### `POST /api/run`

Runs the deterministic ingestion pipeline in a single sync call. No streaming, no session state.

**Request body:**

```json
{
  "manifest_id":   "meta_facebook_ad_insights",
  "tenant_id":     "cliente1",
  "connection_id": "meta-cliente1-acme-mx-abc123",
  "params": {
    "fields":       ["account_id", "campaign_name", "spend"],
    "days_back":    7,
    "target_table": "bronze.meta_facebook_ad_insights_cliente1"
  }
}
```

| Field | Type | Notes |
|---|---|---|
| `manifest_id`   | `string` | Required. Snake_case id from `GET /api/catalog`. |
| `tenant_id`     | `string` | Optional. Selects the row of `~/.mds/tenants.json` and substitutes the `{tenant_id}` token in `bronze_pattern`. Falls back to `"dev"` when empty/missing. |
| `connection_id` | `string` | Optional. If provided, the Cloud Function reads a single JSON secret `{tenant}-{provider}-{connection_id}` (the format produced by the credentials CRUD). When omitted, the CF falls back to the legacy two-secret format (`client_{tenant}_{provider}_{field}`). |
| `params`        | `object` | Connector params, validated against the manifest. **System params** (`target_table`) are allowed even though they are not declared in any manifest. |

**Response 200 (OK or WARN):**

```json
{
  "manifest_id":  "meta_facebook_ad_insights",
  "tenant_id":    "cliente1",
  "target_table": "bronze.meta_facebook_ad_insights_cliente1",
  "ddl":          "CREATE TABLE `bronze.meta_facebook_ad_insights_cliente1` (...)",
  "columns":      ["account_id", "campaign_name", "spend", "ingested_at"],
  "row_count":    654,
  "rows_preview": [{"account_id": "act_123", "campaign_name": "Brand", "spend": 12.5, "ingested_at": "2026-05-27T15:42:13+00:00"}],
  "meta":         {"...": "..."},
  "errors":       [],
  "diagnostics":  {"...": "..."}
}
```

| Field | Notes |
|---|---|
| `target_table`  | Final table name with `{tenant_id}` / `{platform}` / `{connector}` / `{id}` / `{version_major}` tokens substituted. If the user passed `params.target_table`, it wins over the manifest's `bronze_pattern`. |
| `columns`       | Subset requested (or all selectables when `fields: []`). Always includes `ingested_at` (TIMESTAMP) as the last column — stamped by the CF, one value per batch. |
| `rows_preview`  | First 25 rows for the UI. The full record set is written directly to BigQuery by the CF (avoids the 32 MiB CF response limit). |
| `errors`        | Non-fatal connector errors. Empty when fully OK; populated when WARN. |

**Error envelope (4xx / 5xx):**

```json
{
  "error":      "validation_failed",
  "request_id": "8c4f...",
  "node":       "request_validator",
  "reason":     "single-line summary",
  "details":    ["error 1", "error 2"]
}
```

| Code | When | `error` |
|---|---|---|
| 200 | OK or WARN | (success body, no `error` field) |
| 400 | `request_validator` failed: missing required params, unknown manifest_id, `one_of` group not satisfied | `validation_failed` |
| 422 | Body does not parse against `RunRequest` (Pydantic intercept before the handler). Body: `{detail: [...], request_id}` | (Pydantic standard + `request_id`) |
| 502 | Connector failed (upstream 5xx, `status=error` from the connector, CF unreachable) | `connector_failed`, `connector_auth_required`, `connector_forbidden`, `connector_timeout`, `connector_unreachable`, `connector_upstream_error`, `connector_invalid_response` |
| 500 | Unexpected pipeline error | `internal`, `pipeline_failed`, `no_formatted_response` |

**Idempotency:** the CF writes to BigQuery with `WRITE_APPEND` and no de-dupe key. Re-running the same request appends another batch. The `ingested_at` column lets you identify and clean duplicates with `SELECT DISTINCT ingested_at`.

---

## 4. Credentials

CRUD for tenant credentials. Each "connection" is one row in the local SQLite (`mds_credentials.db`) plus one secret in the configured secrets backend (`MDS_SECRETS_BACKEND=local` → JSON file; `gcp` → GCP Secret Manager via gcloud CLI).

**Tenant scoping:** every endpoint reads `X-Tenant-Id` from the request headers; when missing or empty, falls back to `"dev"`. Repository queries always filter by `tenant_id`, so cross-tenant reads are impossible.

**Secret ID convention:** the backend derives `secret_id = sanitize(tenant)-sanitize(provider)-sanitize(connection_id)` (lowercased, non-`[a-z0-9_-]` collapsed to `-`, truncated to 255 with a SHA-1 suffix when longer). The CF mirrors this sanitizer; if you change one, change both.

**Payload shape:** opaque JSON per provider. For `meta` today: `{"access_token": "...", "ad_account_id": "..."}`. The backend never inspects payload contents.

### `PUT /api/credentials/{provider}/{connection_id}`

Upsert a credential. Creates the secret + DB row on first call; on subsequent calls, **merges** the submitted fields into the existing secret (so editing only one field doesn't drop the others) and rotates to a new version.

**Headers:** `X-Tenant-Id: <tenant>` (optional, defaults to `dev`).

**Request body:**

```json
{
  "payload": {"access_token": "EAAxxx...", "ad_account_id": "act_123456789"},
  "name":    "<optional friendly name>"
}
```

`payload` may also be a single string for providers whose secret is one opaque token.

**Response 200:**

```json
{
  "connection": {
    "connection_id": "meta-cliente1-acme-mx-abc123",
    "tenant_id":     "cliente1",
    "provider":      "meta",
    "secret_id":     "cliente1-meta-meta-cliente1-acme-mx-abc123",
    "status":        "active",
    "name":          "Acme MX — Production",
    "created_at":    "2026-05-27T14:11:08+00:00",
    "updated_at":    "2026-05-27T14:11:08+00:00"
  }
}
```

**Errors:** `400 invalid_payload` (payload not serializable / wrong shape), `409 connection_inactive` (existing row is not `active` — re-activate it first via PATCH, or use a new `connection_id`), `502 secret_manager_failed` (backend write to SM / local file failed).

### `GET /api/credentials`

List credentials for the tenant.

**Headers:** `X-Tenant-Id: <tenant>`.
**Query:** `?status=active|inactive|revoked` (optional).

**Response 200:**

```json
{
  "count": 2,
  "connections": [
    {"connection_id": "...", "status": "active", "provider": "meta", "...": "..."}
  ]
}
```

Performs a **lazy health check**: any `active` row whose secret no longer exists in the backend is deleted from the DB before returning.

### `GET /api/credentials/{connection_id}`

Get one credential (metadata only, no payload). `404 connection_not_found` if missing or owned by a different tenant.

### `PATCH /api/credentials/{connection_id}/status`

Transition status. Allowed transitions: `active ↔ inactive`, `active|inactive → revoked`. `revoked` is terminal and additionally disables all secret versions in the backend.

**Request body:**

```json
{"status": "inactive"}
```

**Errors:** `404 connection_not_found`, `409 invalid_status_transition` (e.g. trying to leave `revoked`).

---

## 5. Conventions

### Headers (all responses)

- `X-Request-Id` — uuid4 per request, for tracing. **Log this in the UI when surfacing errors.**
- `Content-Type: application/json`.

### Headers (incoming)

- `X-Tenant-Id` — required by `/api/credentials/*`. Optional for `/api/run` (preferred over the body's `tenant_id` field if both are present).

### BigQuery type → frontend `FieldType` mapping

The manifest exposes raw BigQuery types because the backend uses them to emit DDL. Frontend mapping:

| Manifest type | Frontend `FieldType` |
|---|---|
| `STRING` | `STRING` |
| `INT64` | `INTEGER` |
| `FLOAT64`, `NUMERIC`, `BIGNUMERIC` | `FLOAT` |
| `BOOL` | `BOOLEAN` |
| `DATE`, `DATETIME`, `TIMESTAMP`, `TIME` | `DATE` |
| `JSON`, `BYTES`, `GEOGRAPHY`, `ARRAY`, `STRUCT` | `STRING` (opaque) |

`mode` can be `NULLABLE | REQUIRED | REPEATED`. Today the frontend treats `REPEATED` as `NULLABLE`.

### Security guarantees on the ingestion path

- The payload sent to a Cloud Function is always `{tenant_id, manifest_id, manifest_version, fields?, target_table?, connection_id?, params}`. **Credentials never travel in the payload.** A recursive scrubber drops any key matching `secret|token|password|credential|service_account|private_key|refresh|api_key` (case-insensitive) as defence-in-depth.
- The CF resolves its own secrets from Secret Manager with its SA identity. The backend's only responsibility is to forward `connection_id` (or fall back to the legacy two-secret naming convention when absent).
- Cloud Function id_token resolution order (HTTPBackend): impersonated credentials → service account key (`GOOGLE_APPLICATION_CREDENTIALS`) → `gcloud auth print-identity-token --impersonate-service-account=$MDS_CF_INVOKER_SA`.
- HTTP client timeout: `manifest.limits.max_call_duration_seconds + 20s` buffer, or `560s` default (Cloud Function gen2 max is 540s).

---

## 6. Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `MDS_RUNTIME` | `local` | Dispatcher backend: `local` (in-process imports) \| `http` (real CF) \| `auto` (per-manifest: HTTP if the manifest declares `cloud_function_name`, Local otherwise). |
| `MDS_CF_BASE_URL` | unset | Override the CF host. When loopback (`localhost`/`127.0.0.1`), the HTTPBackend skips id_token signing — useful with `functions-framework` emulator. Empty → canonical `https://{region}-{project}.cloudfunctions.net/{name}`. |
| `MDS_CF_INVOKER_SA` | unset | Service account email to impersonate when fetching the CF id_token via gcloud CLI. Set on developer laptops where ADC is logged in as a user (you need `roles/iam.serviceAccountTokenCreator` over that SA). |
| `MDS_LOCAL_BACKEND_PATHS` | unset | Colon-separated extra roots for `LocalBackend` to resolve connectors from (tests, ad-hoc CI). |
| `MDS_TENANTS_FILE` | `~/.mds/tenants.json` | Path to the tenant registry JSON. |
| `MDS_SECRETS_BACKEND` | `local` | Where to store credential payloads: `local` (file at `MDS_LOCAL_SECRETS_PATH` or `<repo>/.credentials_secrets.json`) \| `gcp` (Secret Manager via gcloud CLI). |
| `MDS_GCP_PROJECT` | `monks-mds-dev` | Project for the `gcp` secrets backend. |
| `MDS_LOCAL_SECRETS_PATH` | `<repo>/.credentials_secrets.json` | Path for the `local` secrets backend. |
| `MDS_DB_PATH` | `<repo>/mds_credentials.db` | Path for the credentials SQLite database. |

---

## 7. Glossary

- **Manifest** — `manifest.json` per connector inside `connectors-library/`. Single source of truth: the UI consumes it for the catalog, the backend for param validation, DDL emission, and dispatch. Schema: `src/ingestion/manifest/schema.json` (Draft 2020-12).
- **Catalog** — in-memory collection of manifests scanned at server start. Lazy cache, invalidated on restart (no hot-reload).
- **LocalBackend / HTTPBackend / AutoBackend** — dispatcher strategies. Local imports the connector module from the submodule (dev). HTTP signs id_tokens via ADC and POSTs to the CF (prod). Auto routes per manifest based on `endpoint.cloud_function_name`.
- **Tenant** — A client. Each tenant has its own row in `~/.mds/tenants.json` (gcp_project + service_account) and its own bundle of secrets in the configured secrets backend. The `{tenant_id}` token in `bronze_pattern` produces tenant-scoped BigQuery tables (`bronze.meta_facebook_ad_insights_cliente1`).
- **Connection** — A specific credential bundle for one (tenant, provider) pair, addressable by `connection_id`. A tenant can have many connections per provider (e.g. one ad account per brand).
- **Bronze** — Raw layer in BigQuery where records land. Defined per manifest in `table_naming.bronze_pattern`.
