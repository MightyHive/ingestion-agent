# Credentials module

Tenant-scoped **connection metadata** lives in a relational database. Sensitive payloads (access tokens, refresh tokens, OAuth grants) are stored in **Google Cloud Secret Manager** in project `monks-mds-dev`. The database stores only a **reference** to each secret (`secret_id`), never the secret value itself.

This document describes the credentials package and its HTTP surface in [`src/api.py`](../api.py). For the full HTTP contract (request/response shapes, status codes), see [`docs/api.md`](../../docs/api.md).

---

## What this module does

| Concern | Where it lives |
|--------|----------------|
| Connection metadata (provider, name, status, timestamps) | SQLite / PostgreSQL table `connections` |
| Secret payloads | GCP Secret Manager |
| Tenant isolation | Every query filters by `tenant_id` |
| HTTP API | `src/api.py` under `/api/credentials/*` |

---

## Project structure

```
src/credentials/
  README.md              ← this file
  __init__.py            ← public exports for library and tests
  lifecycle.py           ← status transition rules and write guards
  resolver.py            ← resolve connection_id into TenantContext for /api/run
  db.py                  ← SQLAlchemy engine, sessions, init_db()
  tables.py              ← ORM model for table `connections`
  schemas.py             ← Pydantic models (ConnectionCreate, ConnectionRecord, ConnectionStatus)
  exceptions.py          ← domain errors (repository + secrets)
  repository.py          ← tenant-scoped SQL CRUD (only place that runs SQL)
  secrets.py               ← secret id building, payload normalization, GCP write/rotate/read
  secrets_backends.py      ← GCP Secret Manager client wrapper
  service.py               ← orchestration used by HTTP handlers (upsert, list, get, status)
  tests/
    conftest.py            ← isolated SQLite session per test run
    test_repository.py      ← repository unit tests
    test_secrets.py          ← secrets API unit tests (mocked GCP)
    test_secrets_gcp.py        ← optional live GCP smoke test (@pytest.mark.gcp)

src/ingestion/tests/
  test_api_credentials.py  ← FastAPI integration tests for /api/credentials/*
```

---

## End-to-end flow

```text
HTTP request (X-Tenant-Id header)
        │
        ▼
src/api.py  (/api/credentials/*)
        │
        ▼
service.py  (upsert_connection, list_connections, get_connection, update_connection_status)
        │
        ├──────────────────────────────┐
        ▼                              ▼
secrets.py (store / rotate)     repository.py (metadata CRUD)
        │                              │
        ▼                              ▼
GcpSecretsBackend                 SQLite / PostgreSQL
(monks-mds-dev)                    table `connections`
```

**Upsert path (create vs update):**

1. Client calls `PUT /api/credentials/{provider}/{connection_id}` with body `{ "payload": ..., "name": "..." }`.
2. Service checks if a row exists for `(tenant_id, connection_id)`.
3. **Create:** `store_connection_secret` → `create_with_connection_id` in repository.
4. **Update:** `rotate_connection_secret` → `update_metadata` in repository.
5. Response returns metadata only (`ConnectionRecord` shape), never the payload.

**Run path (`POST /api/run`):**

1. Client sends `X-Tenant-Id` and `connection_id` in request body.
2. API resolves the manifest, then calls `resolve_for_run(...)`.
3. Resolver validates the connection row (`active`, provider matches manifest).
4. Secret payload is read from Secret Manager (`access_secret_version`) and decoded as JSON object.
5. Graph receives `resolved_tenant` and `connector_runner` invokes dispatcher with that context.

---

## File reference

### `db.py`

- Resolves database URL from environment (see [Configuration](#configuration)).
- Exposes `engine`, `SessionLocal`, `init_db()`, and context manager `get_session()`.
- Default dev database file: `<repo_root>/mds_credentials.db` (gitignored).

### `tables.py`

Defines SQLAlchemy model `ConnectionRow` mapped to table **`connections`**:

| Column | Type | Notes |
|--------|------|--------|
| `connection_id` | `TEXT` PK | Stable id from client URL on upsert; auto-generated UUID on `create()` only |
| `tenant_id` | `TEXT` NOT NULL | Required on every query |
| `provider` | `TEXT` NOT NULL | e.g. `meta`, `dv360` |
| `name` | `TEXT` nullable | Display label |
| `secret_id` | `TEXT` NOT NULL | GCP secret id reference, not the token |
| `status` | `TEXT` NOT NULL | `active`, `inactive`, or `revoked` (CHECK constraint) |
| `created_at`, `updated_at` | `TIMESTAMP` | UTC, set in repository |

Indexes: `(tenant_id)`, `(tenant_id, status)`.

### `schemas.py`

Pydantic models used across repository and API boundaries:

- **`ConnectionStatus`** — enum: `active`, `inactive`, `revoked`.
- **`ConnectionCreate`** — input to create a row: `tenant_id`, `provider`, `secret_id`, optional `name`, optional `status` (defaults to `active`).
- **`ConnectionRecord`** — canonical read model returned by repository and API (no secret fields).

### `exceptions.py`

| Exception | When |
|-----------|------|
| `CredentialsRepositoryError` | Base for persistence errors |
| `ConnectionNotFoundError` | Tenant-scoped lookup misses a row |
| `ConnectionAlreadyExistsError` | Duplicate `connection_id` on create |
| `SecretManagerError` | GCP create/version fails |
| `SecretPayloadError` | Invalid payload type or non-JSON-serializable dict |
| `ConnectionInactiveError` | Run requested with non-active connection |
| `ConnectionProviderMismatchError` | Connection provider does not match manifest platform |
| `InvalidStatusTransitionError` | Illegal status change (e.g. `revoked` → `active`) |

### `repository.py`

**Only module that executes SQL** against `connections`.

| Method | Behavior |
|--------|----------|
| `create(data)` | Inserts row; generates random `connection_id` (UUID) |
| `create_with_connection_id(connection_id, data)` | Inserts row with **client-provided** `connection_id` (used by upsert create path) |
| `get(tenant_id, connection_id)` | One row or `None` |
| `list_by_tenant(tenant_id, status=...)` | All rows for tenant, optional status filter, newest first |
| `update_status(...)` | Lifecycle change |
| `update_metadata(..., name=..., secret_id=...)` | Partial metadata update |

All reads/writes include `tenant_id` in the `WHERE` clause.

### `secrets.py`

Public API for Secret Manager writes:

| Function | Role |
|----------|------|
| `build_secret_id(tenant_id, provider, connection_id)` | Sanitized id: `{tenant}-{provider}-{connection_id}` |
| `secret_resource_name(project_id, secret_id)` | Full resource path helper |
| `get_writer_secrets_backend()` | SM client with **writer** SA (`MDS_SA_CONNECTION_KEY`) |
| `get_reader_secrets_backend()` | SM client with **reader** SA (`MDS_SA_INGESTION_KEY`) |
| `store_connection_secret(...)` | Writer: `ensure_secret` + `add_secret_version` (create path) |
| `rotate_connection_secret(...)` | Writer: `add_secret_version` only (update path) |
| `get_connection_secret(...)` | Reader: `access_secret_version` + decode JSON (run path) |
| `revoke_connection_secret(...)` | Writer: `disable_all_secret_versions` (revocation path) |
| `_normalize_payload(...)` | Accepts `bytes`, `str`, or JSON-serializable `dict` → UTF-8 bytes |

Secret id rules: alphanumeric, hyphen, underscore; segments lowercased; max length 255 (hash suffix if truncated).

### `secrets_backends.py`

- **`SecretsBackend`** — abstract interface: `ensure_secret`, `add_secret_version`, `access_secret_version`.
- **`GcpSecretsBackend`** — uses `google.cloud.secretmanager.SecretManagerServiceClient`; automatic replication; `AlreadyExists` on create is ignored.

### `service.py`

Orchestration for HTTP layer (no FastAPI imports here):

- `upsert_connection` — create or update + secret write/rotate.
- `list_connections` — list metadata for tenant.
- `get_connection` — single record or `ConnectionNotFoundError`.
- `update_connection_status` — lifecycle change with transition rules; on `revoked`, disables all Secret Manager versions.
- Upsert rejects writes when status is `inactive` or `revoked` (`ConnectionInactiveError`).

### `resolver.py`

Runtime resolver used by `POST /api/run`:

- `resolve_for_run(tenant_id, connection_id, expected_platform)`
- Reads tenant-scoped metadata from DB.
- Enforces `status=active` and provider/platform match.
- Reads Secret Manager payload and returns a `TenantContext`.

### `__init__.py`

Re-exports the public surface: DB helpers, repository, schemas, secrets helpers, resolver, and service functions (see `__all__` in the file).

---

## HTTP API (`src/api.py`)

Tenant-scoped routes require:

- **`X-Tenant-Id`** — target tenant.
- **`X-User-Id`** (or `Authorization: Bearer <api_key>`) — caller identity for tenant authorization via `MDS_USER_TENANTS_FILE`.

Responses are metadata-only and include **`X-Request-Id`** for tracing.

| Method | Path | Purpose |
|--------|------|---------|
| `PUT` | `/api/credentials/{provider}/{connection_id}` | Upsert connection + secret payload |
| `GET` | `/api/credentials` | List connections (optional `?status=active\|inactive\|revoked`) |
| `GET` | `/api/credentials/{connection_id}` | Get one connection |
| `PATCH` | `/api/credentials/{connection_id}/status` | Update lifecycle status |
| `POST` | `/api/run` | Run deterministic ingestion using `X-Tenant-Id` + `connection_id` |
| `GET` | `/api/oauth/{provider}/authorize` | Start OAuth code flow (`meta`, `google_ads`) |
| `GET` | `/api/oauth/{provider}/callback` | Exchange code, upsert secret, redirect to frontend |

`POST /api/run` requires:

- Header: `X-Tenant-Id`
- Body: `connection_id` (required)

Run-specific error mapping includes:

- `ConnectionNotFoundError` → `404 connection_not_found`
- `ConnectionInactiveError` → `409 connection_inactive`
- `ConnectionProviderMismatchError` → `400 provider_mismatch`
- `SecretManagerError` → `502 secret_manager_failed`

Auth-specific error mapping includes:

- `MissingUserError` → `401 missing_user`
- `InvalidApiKeyError` → `401 invalid_api_key`
- `UnknownUserError` → `403 unknown_user`
- `TenantAccessDeniedError` → `403 tenant_forbidden`

---

## Configuration

Copy [`.env.example`](../../.env.example) to `.env` and adjust values.

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | — | Full SQLAlchemy URL (production) |
| `MDS_DB_PATH` | — | SQLite file path → `sqlite:///...` |
| (none of above) | `<repo>/mds_credentials.db` | Local dev default |
| `MDS_GCP_PROJECT` | `monks-mds-dev` | GCP project for all secrets (centralized, not per-tenant) |
| `MDS_SA_CONNECTION_KEY` | — | Writer SA JSON: create/rotate/revoke in SM |
| `MDS_SA_INGESTION_KEY` | — | Reader SA JSON: read payloads at `/api/run` |
| `GOOGLE_APPLICATION_CREDENTIALS` | unset | Fallback when role-specific keys are unset |
| `MDS_TENANTS_FILE` | `~/.mds/tenants.json` | Tenant infra fallback (`gcp_project`, `service_account`) |
| `MDS_USER_TENANTS_FILE` | `~/.mds/user_tenants.json` | User → tenant allowlist for API auth |
| `MDS_AUTH_DISABLED` | unset | Optional bypass for local tests/dev only |
| `MDS_OAUTH_STATE_SECRET` | unset | HMAC secret for signed OAuth callback state |
| `META_APP_ID` / `META_APP_SECRET` / `META_OAUTH_REDIRECT_URI` | unset | Meta OAuth code flow |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` / `GOOGLE_OAUTH_REDIRECT_URI` | unset | Google Ads OAuth code flow |
| `MDS_GOOGLE_ADS_DEVELOPER_TOKEN` | unset | Required by Google Ads connector payload |
| `MDS_OAUTH_FRONTEND_SUCCESS_URL` | `http://localhost:3000/credentials-library` | Callback success redirect target |

`api.py` loads `.env` automatically (`python-dotenv`) and calls `init_db()` on app startup.

---

## Layering (how pieces fit together)

```text
  schemas.py          repository.py
  (Pydantic)          (SQL + tenant filter)
        │                    │
        └────────┬───────────┘
                 │
         tables.py ◄── db.py (session)
         (ORM shape)
```

| Layer | Responsibility |
|-------|----------------|
| **schemas** | Validated in-process shapes |
| **tables** | Physical columns and constraints |
| **repository** | Business rules and tenant isolation |
| **secrets** | Payload storage in GCP |
| **resolver** | Build runtime `TenantContext` from DB + Secret Manager |
| **service** | Coordinates DB + secrets for HTTP |
| **api.py** | HTTP transport, headers, error envelopes |

---

## Usage examples

### Library (repository + secrets)

```python
from credentials import (
    ConnectionCreate,
    ConnectionRepository,
    ConnectionStatus,
    get_session,
    init_db,
    store_connection_secret,
)

init_db()

with get_session() as session:
    repo = ConnectionRepository(session)

    connection_id = "my-stable-connection-id"
    secret_id = store_connection_secret(
        tenant_id="acme",
        provider="meta",
        connection_id=connection_id,
        payload={"access_token": "..."},
    )

    record = repo.create_with_connection_id(
        connection_id=connection_id,
        data=ConnectionCreate(
            tenant_id="acme",
            provider="meta",
            secret_id=secret_id,
            name="Meta Ads",
        ),
    )
```

### HTTP (via service + curl)

```bash
export MDS_GCP_PROJECT=monks-mds-dev
export MDS_SA_CONNECTION_KEY=/path/to/sm-credentials-writer.json
export MDS_SA_INGESTION_KEY=/path/to/sm-credentials-reader.json

curl -X PUT "http://localhost:8000/api/credentials/meta/conn-1" \
  -H "X-Tenant-Id: acme" \
  -H "Content-Type: application/json" \
  -d '{"payload":{"access_token":"..."},"name":"Meta production"}'
```

---

## Connection lifecycle (revocation / deactivation)

Three statuses: `active`, `inactive`, `revoked`.

### Allowed transitions

| From | To |
|------|-----|
| `active` | `inactive`, `revoked` |
| `inactive` | `active`, `revoked` |
| `revoked` | *(none — terminal)* |

Use `PATCH /api/credentials/{connection_id}/status` with body `{"status": "inactive"}` or `"revoked"`.

### Runtime behavior

| Status | `POST /api/run` | `PUT` upsert (rotate secret) |
|--------|-----------------|------------------------------|
| `active` | Allowed (if provider matches) | Allowed |
| `inactive` | `409 connection_inactive` | `409 connection_inactive` |
| `revoked` | `409 connection_inactive` | `409 connection_inactive` |

Reactivate a paused connection: `PATCH` → `active`, then upsert again if tokens changed.

### Secret Manager deletion policy

Secrets live in project **`monks-mds-dev`**. The metadata DB never stores token values.

| Status | Secret Manager resource | Versions / payload |
|--------|-------------------------|-------------------|
| **`inactive`** | Secret **retained** | All versions **unchanged** and still readable if accessed directly. Only the API blocks run and upsert via DB `status`. |
| **`revoked`** | Secret **retained** (not auto-deleted) | On transition to `revoked`, the API calls **`disable_secret_version`** on every **enabled** version. `access_secret_version` / `latest` fails after that. |
| **Post-revoke cleanup** | Manual / ops | After a retention window (e.g. 30 days), ops may call [`delete_secret`](https://cloud.google.com/secret-manager/docs/delete-secrets) on the secret resource. This is **out of band** — not performed by the app on PATCH. |

Rationale: disabling versions immediately cuts off ingestion without destroying audit history; delayed `delete_secret` matches GCP compliance and recovery practices.

IAM: the credentials **writer** SA needs `secretmanager.versions.disable` (and list) for revoke; the **reader** SA used at run time only needs `secretmanager.versions.access` on active connections.

---

## Security conventions

1. **No tokens in the database** — only `secret_id` pointers.
2. **No secret fields in API responses** — only `ConnectionRecord` metadata.
3. **Tenant isolation** — repository always scopes by `tenant_id`; cross-tenant access returns `None` or `ConnectionNotFoundError`.
4. **Do not log request bodies** that contain tokens.
5. **Tenant authorization is enforced before DB/SM access** on `/api/credentials/*`, `/api/run`, and `/api/oauth/*`.

---

## OAuth onboarding

OAuth onboarding is implemented for `meta` and `google_ads` providers:

1. Caller hits `GET /api/oauth/{provider}/authorize` with `X-User-Id` + `X-Tenant-Id` and `connection_id`.
2. API signs `state` (`tenant_id`, `connection_id`, `provider`, `user_id`, expiry) and redirects to provider authorize URL.
3. Provider redirects to `GET /api/oauth/{provider}/callback?code=...&state=...`.
4. API validates signed state, exchanges `code` for tokens, and upserts secret payload + metadata.
5. API redirects to `MDS_OAUTH_FRONTEND_SUCCESS_URL` with query params (`oauth=success`, `provider`, `connection_id`).

The manual path `PUT /api/credentials/{provider}/{connection_id}` stays available for local/testing workflows.

---

## Tests

From repo root:

```bash
# Repository + secrets (unit; secrets tests mock GCP)
pytest src/credentials/tests -q

# HTTP credentials API (isolated DB + mocked secrets)
pytest src/ingestion/tests/test_api_credentials.py -q

# Optional: live GCP write/rotate (requires credentials + project access)
pytest src/credentials/tests -m gcp -q
```

| Test file | What it covers |
|-----------|----------------|
| `test_repository.py` | CRUD, tenant isolation, status filter, `create_with_connection_id` |
| `test_secrets.py` | `build_secret_id`, store/rotate/revoke with fake backend, payload validation |
| `test_lifecycle.py` | Status transition matrix |
| `test_service.py` | Upsert guards, revoke orchestration |
| `test_secrets_gcp.py` | Live GCP smoke (skipped without `GOOGLE_APPLICATION_CREDENTIALS`) |
| `test_api_credentials.py` | Upsert create/update, list/get, status patch, missing header, error mapping |

Repository tests use a **temporary SQLite file** per run (`tests/conftest.py`), not the global `mds_credentials.db`.

---

## Related documentation

- HTTP contract details: [`docs/api.md`](../../docs/api.md)
- Environment template: [`.env.example`](../../.env.example)

When extending this module, update this README and `docs/api.md` together.