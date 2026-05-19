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
  db.py                  ← SQLAlchemy engine, sessions, init_db()
  tables.py              ← ORM model for table `connections`
  schemas.py             ← Pydantic models (ConnectionCreate, ConnectionRecord, ConnectionStatus)
  exceptions.py          ← domain errors (repository + secrets)
  repository.py          ← tenant-scoped SQL CRUD (only place that runs SQL)
  secrets.py               ← secret id building, payload normalization, GCP write/rotate
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
| `get_secrets_backend()` | Returns `GcpSecretsBackend` using `MDS_GCP_PROJECT` |
| `store_connection_secret(...)` | `ensure_secret` + `add_secret_version` (create path) |
| `rotate_connection_secret(...)` | `add_secret_version` only (update path) |
| `_normalize_payload(...)` | Accepts `bytes`, `str`, or JSON-serializable `dict` → UTF-8 bytes |

Secret id rules: alphanumeric, hyphen, underscore; segments lowercased; max length 255 (hash suffix if truncated).

### `secrets_backends.py`

- **`SecretsBackend`** — abstract interface: `ensure_secret`, `add_secret_version`.
- **`GcpSecretsBackend`** — uses `google.cloud.secretmanager.SecretManagerServiceClient`; automatic replication; `AlreadyExists` on create is ignored.

### `service.py`

Orchestration for HTTP layer (no FastAPI imports here):

- `upsert_connection` — create or update + secret write/rotate.
- `list_connections` — list metadata for tenant.
- `get_connection` — single record or `ConnectionNotFoundError`.
- `update_connection_status` — PATCH status equivalent at service level.

### `__init__.py`

Re-exports the public surface: DB helpers, repository, schemas, secrets helpers, and service functions (see `__all__` in the file).

---

## HTTP API (`src/api.py`)

All routes require header **`X-Tenant-Id`**. Responses are metadata-only and include **`X-Request-Id`** for tracing.

| Method | Path | Purpose |
|--------|------|---------|
| `PUT` | `/api/credentials/{provider}/{connection_id}` | Upsert connection + secret payload |
| `GET` | `/api/credentials` | List connections (optional `?status=active\|inactive\|revoked`) |
| `GET` | `/api/credentials/{connection_id}` | Get one connection |
| `PATCH` | `/api/credentials/{connection_id}/status` | Update lifecycle status |

Error mapping in API: `SecretPayloadError` → 400, `ConnectionNotFoundError` → 404, `SecretManagerError` → 502.

---

## Configuration

Copy [`.env.example`](../../.env.example) to `.env` and adjust values.

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | — | Full SQLAlchemy URL (production) |
| `MDS_DB_PATH` | — | SQLite file path → `sqlite:///...` |
| (none of above) | `<repo>/mds_credentials.db` | Local dev default |
| `MDS_GCP_PROJECT` | `monks-mds-dev` | GCP project for all secrets |
| `GOOGLE_APPLICATION_CREDENTIALS` | unset | Service account JSON for GCP API calls |

Schema bootstrap: call `init_db()` once (e.g. on app startup) before using the repository.

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
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json

curl -X PUT "http://localhost:8000/api/credentials/meta/conn-1" \
  -H "X-Tenant-Id: acme" \
  -H "Content-Type: application/json" \
  -d '{"payload":{"access_token":"..."},"name":"Meta production"}'
```

---

## Security conventions

1. **No tokens in the database** — only `secret_id` pointers.
2. **No secret fields in API responses** — only `ConnectionRecord` metadata.
3. **Tenant isolation** — repository always scopes by `tenant_id`; cross-tenant access returns `None` or `ConnectionNotFoundError`.
4. **Do not log request bodies** that contain tokens.

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
| `test_secrets.py` | `build_secret_id`, store/rotate with fake backend, payload validation |
| `test_secrets_gcp.py` | Live GCP smoke (skipped without `GOOGLE_APPLICATION_CREDENTIALS`) |
| `test_api_credentials.py` | Upsert create/update, list/get, status patch, missing header, error mapping |

Repository tests use a **temporary SQLite file** per run (`tests/conftest.py`), not the global `mds_credentials.db`.

---

## Related documentation

- HTTP contract details: [`docs/api.md`](../../docs/api.md)
- Environment template: [`.env.example`](../../.env.example)

When extending this module, update this README and `docs/api.md` together.