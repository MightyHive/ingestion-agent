# dv360-fetch — Cloud Function

Cloud Function gen2 (HTTP, private) that wraps the DV360 Bid Manager
Reports connector for the MDS Fase 5 pipeline. It is the runtime
counterpart of `HTTPBackend` on the MDS backend side.

## What it does

Given a single HTTP POST from the MDS backend:

1. Validates `tenant_id`, `manifest_id`, and `params`.
2. Resolves the tenant's two DV360 secrets from Secret Manager using
   the Cloud Function's own identity (`mds-cf-runner`):
   - `client_<tenant_id>_dv360_query_id`
   - `client_<tenant_id>_dv360_service_account_json`
3. Calls `dv360_reports.fetch(params, context)` (the existing
   connector module, vendored in at deploy time).
4. If `target_table` was provided and rows came back, writes them to
   BigQuery using the schema derived from `manifest.available_fields`
   (with `STRING` fallback for unknown columns).
5. Returns a JSON body in the standard MDS connector response shape:
   `{status, code, records (capped preview), meta, errors}`.

The CF **never receives credentials in the request body**. The MDS
backend's HTTPBackend actively scrubs anything credential-shaped from
the wire — see `src/ingestion/dispatcher/http.py::_scrub_secret_keys`.

## Layout

```
cloud-functions/dv360-fetch/
├── main.py            # CF entrypoint (functions-framework HTTP, target=run)
├── requirements.txt   # CF runtime deps
├── .gcloudignore      # excludes tests + local artefacts from upload
├── deploy.sh          # stage + deploy script (see "Deploy")
├── conftest.py        # hermetic test setup (stubs functions-framework + GCP SDKs)
├── test_main.py       # 34 unit tests, no GCP access required
└── README.md          # this file
```

At deploy time, `deploy.sh stage` adds:

```
.staging/
├── (all of the above except tests)
├── dv360_reports.py   # vendored from connectors-library/dv360/reports/
├── api_handler.py     # vendored from connectors-library/dv360/reports/
└── manifest.json      # vendored from connectors-library/dv360/manifest.json
```

`gcloud functions deploy --source=.staging` then uploads only that
directory, so the deployed artefact is fully self-contained.

## Deploy

Prerequisites (set up in B0/B1):

- `gcloud config set project monks-mds-dev`
- `gcloud auth application-default login` (for the calling identity)
- Secrets `client_<tenant_id>_dv360_query_id` and
  `client_<tenant_id>_dv360_service_account_json` created in Secret
  Manager (B2).
- Service account `mds-cf-runner@monks-mds-dev.iam.gserviceaccount.com`
  with:
  - `roles/secretmanager.secretAccessor` on both secrets
  - `roles/bigquery.dataEditor` on the target dataset
  - `roles/bigquery.jobUser` at the project level

Deploy:

```bash
cd cloud-functions/dv360-fetch
./deploy.sh deploy
```

Equivalent `gcloud` invocation (run by `deploy.sh`):

```bash
gcloud functions deploy dv360-fetch \
    --gen2 \
    --project=monks-mds-dev \
    --region=us-central1 \
    --runtime=python311 \
    --source=./.staging \
    --entry-point=run \
    --trigger-http \
    --no-allow-unauthenticated \
    --service-account=mds-cf-runner@monks-mds-dev.iam.gserviceaccount.com \
    --memory=1Gi \
    --timeout=540s \
    --max-instances=5 \
    --set-env-vars=GCP_PROJECT=monks-mds-dev
```

Override any of `CF_NAME`, `CF_REGION`, `CF_PROJECT`, `CF_SA`,
`CF_MEMORY`, `CF_TIMEOUT`, `CF_MAX_INSTANCES` via env vars before
running the script.

## Local smoke (no real GCP roundtrip)

`deploy.sh smoke` runs the CF locally under `functions-framework`. The
MDS backend's `HTTPBackend` skips the id_token fetch for loopback URLs,
so this gives you the full plumbing test without ADC:

```bash
# Terminal 1 — start the CF locally
cd cloud-functions/dv360-fetch
./deploy.sh smoke
# Listening on http://localhost:8080/

# Terminal 2 — point the backend at it
export MDS_RUNTIME=http
export MDS_CF_BASE_URL=http://localhost:8080
cd ../..
# ... start backend as usual ...
```

For the SM/BQ paths to actually work locally you also need
`GOOGLE_APPLICATION_CREDENTIALS` set (or ADC via
`gcloud auth application-default login`) so the function can talk to
the real Secret Manager + BigQuery. If you want a pure-plumbing smoke
without GCP, monkey-patch `_resolve_secret` and `_write_records_to_bq`
in a local `_smoke_override.py` (gitignored).

## Running the tests

The tests are fully hermetic — they install no GCP SDKs and run in
under a second:

```bash
cd cloud-functions/dv360-fetch
pytest test_main.py -v
```

What's covered (`test_main.py`, 34 tests):

- Body-validation guards: missing/wrong `tenant_id`, `manifest_id`,
  `params`.
- Secret resolution: secret-name pattern (`client_<id>_dv360_*`),
  `MISSING_SECRET` on SM failure.
- Connector error code → HTTP status mapping (`UNAUTHORIZED`/401,
  `FORBIDDEN`/403, `POLL_TIMEOUT`/504, etc.).
- `CONNECTOR_RAISED` wrapping for unexpected exceptions.
- `CONNECTOR_NOT_PACKAGED` when `dv360_reports` is missing (i.e. the
  deploy didn't stage the connector — a real failure mode).
- Happy path with and without `target_table`.
- `fields` top-level → `params.fields` re-injection.
- BQ write happy path, table-id normalisation (`dataset.table` →
  `project.dataset.table`), invalid `target_table` rejection.
- `BQ_WRITE_FAILED` wrapping on BigQuery errors.
- Records preview cap (`RECORDS_PREVIEW_CAP`) + cap metadata.
- Schema derivation: manifest types for known columns, `STRING`
  default for unknown.

## Cloud Function I/O contract

### Request body

```json
{
    "tenant_id":        "acme",
    "manifest_id":      "dv360_reports",
    "manifest_version": "0.1.0",
    "fields":           ["Impressions", "Clicks"],
    "target_table":     "bronze.dv360_reports",
    "params": {
        "data_range":        "LAST_7_DAYS",
        "customStartDate":   "20260101",
        "customEndDate":     "20260131",
        "poll_timeout_sec":  400,
        "poll_interval_sec": 10
    }
}
```

`fields` and `target_table` are top-level (lifted from `params` by the
MDS backend so the CF can read them without spelunking).

### Response body

```json
{
    "status":  "OK",
    "code":    "FETCH_OK",
    "records": [{"Impressions": 1234, "Clicks": 12, "Date": "2026/05/19"}],
    "meta": {
        "query_id":       "1234567",
        "report_id":      "98765",
        "gcs_path":       "https://storage.googleapis.com/dv360-reports/...",
        "data_range":     "LAST_7_DAYS",
        "fields_requested": "all",
        "total_rows":     1234,
        "bq_table_id":    "monks-mds-dev.bronze.dv360_reports",
        "rows_written":   1234,
        "schema_created": false,
        "tenant_id":      "acme",
        "manifest_id":    "dv360_reports",
        "records_total":  1234
    },
    "errors": []
}
```

When `records_total` exceeds `RECORDS_PREVIEW_CAP` (200), `records`
holds the first 200 rows only and `meta.records_preview_capped_at`
is set. The complete data set is in BigQuery.

### Error responses

| HTTP | `code`                    | Meaning                                              |
|-----:|---------------------------|------------------------------------------------------|
|  400 | `MISSING_TENANT_ID`       | body.tenant_id missing or not a string               |
|  400 | `MISSING_MANIFEST_ID`     | body.manifest_id missing or not a string             |
|  400 | `MANIFEST_MISMATCH`       | this CF only handles `dv360_reports`                 |
|  400 | `INVALID_PARAMS`          | body.params not an object                            |
|  400 | `INVALID_TARGET_TABLE`    | target_table not `dataset.table` / `proj.ds.table`   |
|  400 | `MISSING_QUERY_ID`        | connector signalled missing query id (rare — SM)     |
|  401 | `UNAUTHORIZED`            | connector reports auth rejected                      |
|  401 | `INVALID_CREDENTIALS`     | SA JSON malformed                                    |
|  401 | `MISSING_CREDENTIALS`     | no SA JSON resolved                                  |
|  403 | `FORBIDDEN`               | DV360 returned 403                                   |
|  500 | `MISSING_SECRET`          | Secret Manager call failed                           |
|  500 | `CONNECTOR_NOT_PACKAGED`  | `dv360_reports` import failed inside CF              |
|  500 | `CONNECTOR_RAISED`        | connector raised an unexpected exception             |
|  500 | `BQ_WRITE_FAILED`         | BigQuery load job failed                             |
|  504 | `POLL_TIMEOUT`            | DV360 report did not reach DONE in time              |

## Operational notes

- **Cold start**: ~3-5s including google-cloud-bigquery + google-cloud-secret-manager
  initialisation. Both clients are lazy-imported inside the helpers, so cold
  starts that hit MISSING_SECRET don't pay the BQ import cost.
- **Concurrency**: defaults to `max-instances=5`. Each instance is a
  single Python process; gen2 supports `--concurrency` if we ever need
  to batch.
- **Timeout**: 540s (DV360 typically finishes <120s, but quarterly
  pulls have hit ~400s). The MDS backend uses
  `limits.max_call_duration_seconds + 20s = 560s` as its client-side
  timeout (`HTTPBackend._resolve_timeout`).
- **Logs**: structured logs land in Cloud Logging. Search by
  `resource.labels.function_name="dv360-fetch"`. The most useful
  filters are `severity>=ERROR` (errors) and
  `jsonPayload.tenant_id="<id>"` (per-tenant trace).

## Related code

- `src/ingestion/dispatcher/http.py` — HTTPBackend (caller side).
- `connectors-library/dv360/reports/dv360_reports.py` — the actual
  connector (`fetch()` entry point).
- `connectors-library/dv360/manifest.json` — SSoT for fields, secret
  names, endpoint definition.
- `docs/mvp-phase5-checklist.md` — B4 task tracker.
