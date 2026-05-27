# MDS — Operational Runbook

> Day-to-day operations for the MVP: re-deploy the Cloud Function, smoke the end-to-end flow, troubleshoot common failures, and plan the next step toward production.
>
> For first-time setup of a developer machine, see [`onboarding-local.md`](onboarding-local.md). For API shapes, see [`api.md`](api.md).

## Index

1. [Re-deploy the Cloud Function (Meta Facebook)](#1-re-deploy-the-cloud-function-meta-facebook)
2. [Smoke the end-to-end flow](#2-smoke-the-end-to-end-flow)
3. [Credentials operations](#3-credentials-operations)
4. [Troubleshooting matrix](#4-troubleshooting-matrix)
5. [Path to production (post-MVP)](#5-path-to-production-post-mvp)

---

## 1. Re-deploy the Cloud Function (Meta Facebook)

Triggered whenever `cloud-functions/meta-facebook-insights/` changes (handler, requirements, vendored connector).

```bash
cd cloud-functions/meta-facebook-insights

gcloud functions deploy meta-facebook-insights \
  --gen2 \
  --runtime=python311 \
  --region=us-central1 \
  --source=. \
  --entry-point=run \
  --trigger-http \
  --no-allow-unauthenticated \
  --service-account=mds-cf-meta@monks-mds-dev.iam.gserviceaccount.com \
  --set-env-vars=GCP_PROJECT=monks-mds-dev \
  --memory=512MB \
  --timeout=540s \
  --project=monks-mds-dev
```

**Validate post-deploy** (hits the CF directly with an ADC id_token — bypasses the backend):

```bash
URL=$(gcloud functions describe meta-facebook-insights \
  --region=us-central1 --gen2 --project=monks-mds-dev --format='value(serviceConfig.uri)')

TOKEN=$(gcloud auth print-identity-token --audiences="$URL")

curl -s -X POST "$URL" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "cliente1",
    "manifest_id": "meta_facebook_ad_insights",
    "manifest_version": "0.1.0",
    "connection_id": "<your connection id, or omit for legacy 2-secret format>",
    "target_table": "bronze.meta_facebook_ad_insights_cliente1",
    "fields": ["account_id","campaign_name","spend","impressions"],
    "params": {"days_back": 7}
  }' | python -m json.tool
```

**Confirm `ingested_at` lands as the last BigQuery column (TIMESTAMP):**

```bash
bq show --format=prettyjson monks-mds-dev:bronze.meta_facebook_ad_insights_cliente1 \
  | python -c "import sys,json;s=json.load(sys.stdin)['schema']['fields'];print('\n'.join(f\"{i+1:>2}. {f['name']} ({f['type']})\" for i,f in enumerate(s)))"
```

The Cloud Function supports two secret formats:

- **New format** (when `connection_id` is in the payload): one JSON secret named `{tenant}-meta-{connection_id}` carrying `{access_token, ad_account_id}`. This is what the credentials CRUD creates.
- **Legacy fallback** (when `connection_id` is omitted): two flat secrets `client_{tenant}_meta_access_token` and `client_{tenant}_meta_ad_account_id`.

Both paths run today; new connections go through the CRUD, the legacy path stays available for tenants whose secrets were bootstrapped by hand.

---

## 2. Smoke the end-to-end flow

Run after re-deploying the CF or after any backend change that touches `src/ingestion/` or `src/api.py`.

**Start the backend:**

```bash
cd ~/Monks/Agentes/ingestion-agent
source .venv/bin/activate
export MDS_RUNTIME=http   # or "auto" — the manifest has cloud_function_name set
cd src
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

(`cd src` then `uvicorn api:app` is intentional — `ingestion` is a top-level package inside `src/`. Running `uvicorn src.api:app` from the repo root raises `ModuleNotFoundError: No module named 'ingestion'`.)

**Hit `/api/run` with the active piloto credential:**

```bash
curl -s -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{
    "manifest_id":   "meta_facebook_ad_insights",
    "tenant_id":     "cliente1",
    "connection_id": "<your active connection id>",
    "params": {
      "fields":    ["account_id","campaign_name","spend","impressions"],
      "days_back": 7
    }
  }' | python -m json.tool
```

**Expected:**

- `target_table: "bronze.meta_facebook_ad_insights_cliente1"` (the `{tenant_id}` token was substituted from `bronze_pattern`).
- `row_count > 0`.
- `columns` includes `ingested_at` as the last element.
- BigQuery query confirms a fresh `MAX(ingested_at)` row:

```bash
bq query --use_legacy_sql=false \
  "SELECT COUNT(*) AS rows, MAX(ingested_at) AS last_batch
   FROM \`monks-mds-dev.bronze.meta_facebook_ad_insights_cliente1\`"
```

**Override the target table** (validates the system param):

```bash
curl -s -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{
    "manifest_id": "meta_facebook_ad_insights",
    "tenant_id":   "cliente1",
    "params": {
      "fields":       ["account_id","campaign_name","spend"],
      "days_back":    7,
      "target_table": "sandbox.meta_adhoc_test"
    }
  }' | python -m json.tool
```

`target_table` in the response must be `sandbox.meta_adhoc_test` (the override wins over the manifest default).

---

## 3. Credentials operations

The credentials CRUD lives in `src/credentials/` (DB + secrets backends + service) and surfaces via `/api/credentials/*` (see [`api.md` §4](api.md#4-credentials)).

### Local development

```bash
export MDS_SECRETS_BACKEND=local           # default — payloads in <repo>/.credentials_secrets.json
# (override DB location if needed)
export MDS_DB_PATH=/tmp/mds_credentials.db
```

The first time the backend starts (`init_db` runs in the FastAPI `lifespan` hook), SQLAlchemy creates the `connections` table. Restart `uvicorn` if you change `MDS_DB_PATH`.

### Production / piloto (GCP Secret Manager)

```bash
export MDS_SECRETS_BACKEND=gcp
export MDS_GCP_PROJECT=monks-mds-dev
```

The `gcp` backend shells out to `gcloud secrets`. ADC must be logged in as a user (or SA) with `roles/secretmanager.admin` (for create/disable) and `roles/secretmanager.secretAccessor` (for read).

### Importing legacy secrets

If a tenant already has secrets in Secret Manager from the pre-CRUD era (the flat `client_<tenant>_<provider>_<field>` convention), bring them under the CRUD:

```bash
PYTHONPATH=src python src/scripts/import_gcp_secrets.py \
  --project monks-mds-dev \
  --tenants dev,cliente1
```

The script reads existing secrets, groups them by `(tenant, provider)`, and writes new JSON-bundled secrets in the format the CRUD expects (`{tenant}-{provider}-{connection_id}`), plus the matching `connections` DB rows. The legacy secrets are left in place — the Cloud Function still falls back to them when `connection_id` is absent.

### Rotation, revocation

- **Rotation:** another `PUT /api/credentials/{provider}/{connection_id}` with the new payload merges into the existing secret and adds a new version. The CF reads `latest`, so the next run picks up the new value.
- **Revocation:** `PATCH /api/credentials/{connection_id}/status` with `{"status": "revoked"}` disables every secret version in the backend before flipping the row. Revoked is terminal — to use that `connection_id` again, pick a different one.
- **Soft deactivation:** the UI's "delete" button issues `PATCH {"status": "inactive"}`. The row stays in the DB. To bring it back, re-activate via PATCH; to use the same `connection_id` for a brand new credential, deactivate then revoke, then create with a new `connection_id`.

---

## 4. Troubleshooting matrix

| Symptom | Likely cause | Fix |
|---|---|---|
| `tenants file not found at ~/.mds/tenants.json` | Skipped onboarding step | Follow [`onboarding-local.md`](onboarding-local.md) §4 |
| `PermissionDenied` from `gcloud auth application-default print-access-token` | Missing `roles/iam.serviceAccountTokenCreator` over `mds-cf-runner` | Ask Ivan for the role on that SA |
| `/api/run` returns 502 `connector_auth_unavailable: could not obtain an id_token` | The HTTPBackend cannot fetch an id_token for the CF audience | Set `MDS_CF_INVOKER_SA=mds-cf-meta@monks-mds-dev.iam.gserviceaccount.com` in `.env`, or set `GOOGLE_APPLICATION_CREDENTIALS` to a SA key file |
| `/api/run` returns 502 `connector_forbidden` | Caller SA lacks `roles/cloudfunctions.invoker` on the CF | Grant the role to whichever SA you are impersonating |
| CF logs show `MISSING_SECRET` | The secret the CF tried to read does not exist (either the JSON-format `{tenant}-{provider}-{connection_id}` or the legacy `client_{tenant}_{provider}_{field}`) | Create the credential via the UI (`/api/credentials`) for the active tenant, or bootstrap the legacy secrets with `gcloud secrets create` |
| `/api/credentials` returns 409 `connection_inactive` on PUT | A previously deactivated/revoked row exists with that `connection_id` | Either `PATCH status=active` to revive it, or use a new `connection_id` |
| Frontend: CLIENT dropdown empty | `NEXT_PUBLIC_TENANTS` not set in `frontend/.env.local` | Copy from `frontend/.env.example` |
| `npx tsc --noEmit` errors | Stale `node_modules` or type drift after pull | `npm install`, then re-run |
| BigQuery table missing `ingested_at` | CF was not re-deployed after the `ingested_at` change | Re-deploy per §1 |

---

## 5. Path to production (post-MVP)

The MVP runs the backend on a developer Mac, the CF in `monks-mds-dev`, secrets in Secret Manager or a local JSON file, and the SQLite DB on disk. To put MDS in front of real users:

| Component | Recommendation | Why |
|---|---|---|
| **Connector CFs** | Keep on Cloud Functions gen2 (already there) | Per-connector isolation, tolerable cold start, independent deploys |
| **Backend (FastAPI)** | **Cloud Run** | Long-running HTTP server, not a fit for CF; gives 0→N autoscale, native IAM auth, custom domain via load balancer |
| **Frontend (Next.js)** | Cloud Run (SSR) or Firebase Hosting (static) | Mili decides based on the SSR posture |
| **`tenants.json`** | **Secret Manager** behind `MDS_TENANTS_FILE` / a new `MDS_TENANTS_SOURCE` flag | No FS dependency in prod; loader is already mockable (`set_loader_for_testing`) |
| **Credentials DB** | Cloud SQL (Postgres) — keep SQLAlchemy, change the URL | SQLite on Cloud Run dies on every redeploy |
| **Credentials secrets backend** | `MDS_SECRETS_BACKEND=gcp` permanently | Stop using the local JSON backend |
| **CORS** | Restrict to the frontend domain | Today `allow_origins=["*"]` |
| **Auth (UI → API)** | IAP (Identity-Aware Proxy) or Firebase Auth + id_token verification | Pick when there is a real user model |

**Suggested order:**

1. Containerize the backend (slim `Dockerfile` with uvicorn).
2. Implement the Secret Manager loader for tenants behind a flag.
3. Migrate the credentials DB to Cloud SQL.
4. Close CORS and pin allowed origins.
5. `gcloud run deploy mds-api --source=. --region=us-central1 --no-allow-unauthenticated --service-account=mds-api-prod@...`.
6. Grant the Cloud Run SA `roles/cloudfunctions.invoker` on every connector CF (so HTTPBackend can sign id_tokens server-side without `gcloud` CLI).
7. Deploy the frontend separately, set the backend base URL via a build-time env var.

None of this is on the immediate critical path — file as a follow-up when the MVP graduates.
