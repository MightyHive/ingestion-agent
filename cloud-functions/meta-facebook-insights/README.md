# meta-facebook-insights — Cloud Function

Cloud Function gen2 (HTTP, private) that wraps the Meta Marketing API
(Facebook Ads) Insights connector for the MDS Fase 5 pipeline. It is
the runtime counterpart of `HTTPBackend` on the MDS backend side, and
the second member of the "one CF per connector" pattern that started
with `dv360-fetch`.

## What it does

Given a single HTTP POST from the MDS backend:

1. Validates `tenant_id`, `manifest_id`, and `params`.
2. Resolves the tenant's two Meta secrets from Secret Manager using
   the Cloud Function's own identity (`mds-cf-runner`):
   - `client_<tenant_id>_meta_access_token`  (Meta System User token)
   - `client_<tenant_id>_meta_ad_account_id` (e.g. `act_1234567890`)
3. Calls `facebook_ads.fetch(params, context)` (the existing connector
   module, vendored in at deploy time).
4. The connector returns a 3-level dict of records:
   `{"campaigns": [...], "adsets": [...], "ads": [...]}`. The CF picks
   the level named by `manifest.metadata.response_subkey` (default
   `"ads"`) for the BQ write + the response preview.
5. If `target_table` was provided and the selected level has rows,
   writes them to BigQuery using the schema derived from
   `manifest.available_fields` (with `STRING` fallback for unknown
   columns; FLOAT64/NUMERIC/DATE/JSON come from the manifest).
6. Returns a JSON body in the standard MDS connector response shape:
   `{status, code, records (capped preview of selected level), meta,
   errors}`. `meta` carries total counts for all three levels
   (`total_campaigns`, `total_adsets`, `total_ads`) and the
   `response_subkey` used.

The CF **never receives credentials in the request body**. The MDS
backend's HTTPBackend actively scrubs anything credential-shaped from
the wire — see `src/ingestion/dispatcher/http.py::_scrub_secret_keys`.

## Layout

```
cloud-functions/meta-facebook-insights/
├── main.py            # CF entrypoint (functions-framework HTTP, target=run)
├── requirements.txt   # CF runtime deps
├── .gcloudignore      # excludes tests + local artefacts from upload
├── deploy.sh          # stage + deploy script (see "Deploy")
├── conftest.py        # hermetic test setup (stubs functions-framework + GCP SDKs)
├── test_main.py       # 37 unit tests, no GCP access required
└── README.md          # this file
```

At deploy time, `deploy.sh stage` adds:

```
.staging/
├── (all of the above except tests)
├── facebook_ads.py    # vendored from connectors-library/meta/facebook/
├── api_handler.py     # vendored from connectors-library/meta/facebook/
└── manifest.json      # vendored from connectors-library/meta/facebook/
```

`gcloud functions deploy --source=.staging` then uploads only that
directory, so the deployed artefact is fully self-contained.

## Deploy

Prerequisites (Meta credentials bootstrapped 2026-05-20):

- `gcloud config set project monks-mds-dev`
- `gcloud auth application-default login` (for the calling identity)
- Secrets `client_<tenant_id>_meta_access_token` and
  `client_<tenant_id>_meta_ad_account_id` created in Secret Manager.
- Service account `mds-cf-runner@monks-mds-dev.iam.gserviceaccount.com`
  with:
  - `roles/secretmanager.secretAccessor` on both secrets (granted
    per-secret, not project-wide — see `docs/architecture.md`).
  - `roles/bigquery.dataEditor` on the target dataset
  - `roles/bigquery.jobUser` at the project level

Deploy:

```bash
cd cloud-functions/meta-facebook-insights
./deploy.sh deploy
```

Equivalent `gcloud` invocation (run by `deploy.sh`):

```bash
gcloud functions deploy meta-facebook-insights \
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
cd cloud-functions/meta-facebook-insights
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
the real Secret Manager + BigQuery + Meta Graph API. If you want a
pure-plumbing smoke without GCP, monkey-patch `_resolve_secret` and
`_write_records_to_bq` in a local `_smoke_override.py` (gitignored).

## Running the tests

The tests are fully hermetic — they install no GCP SDKs and run in
under a second:

```bash
cd cloud-functions/meta-facebook-insights
pytest test_main.py -v
```

What's covered (`test_main.py`, 37 tests):

- Body-validation guards: missing/wrong `tenant_id`, `manifest_id`,
  `params`.
- Secret resolution: secret-name pattern (`client_<id>_meta_*`),
  `MISSING_SECRET` on SM failure.
- Connector error code → HTTP status mapping (Meta-specific:
  `UNAUTHORIZED`/401, `MISSING_CREDENTIALS`/401, `FORBIDDEN`/403,
  `MISSING_ACCOUNT_ID`/400, `INVALID_PARAMS`/400,
  `UNEXPECTED_ERROR`/500).
- `CONNECTOR_RAISED` wrapping for unexpected exceptions.
- `CONNECTOR_NOT_PACKAGED` when `facebook_ads` is missing (i.e. the
  deploy didn't stage the connector — a real failure mode).
- Multi-level records dict: `response_subkey` selection, BQ writes
  ONLY the selected level, totals for all three levels surface in
  `meta`.
- Happy path with and without `target_table`.
- `fields` top-level → `params.fields` re-injection.
- BQ write happy path, table-id normalisation (`dataset.table` →
  `project.dataset.table`), invalid `target_table` rejection.
- BQ skipped when the SELECTED level is empty (even if other levels
  have rows).
- `BQ_WRITE_FAILED` wrapping on BigQuery errors.
- Records preview cap (`RECORDS_PREVIEW_CAP`) + cap metadata applied
  to the selected level.
- Schema derivation: manifest types for known columns
  (FLOAT64/NUMERIC/DATE/JSON), `STRING` default for unknown.

## Cloud Function I/O contract

### Request body

```json
{
    "tenant_id":        "cliente1",
    "manifest_id":      "meta_facebook_ad_insights",
    "manifest_version": "0.1.0",
    "fields":           ["ad_id", "impressions", "spend", "date_start"],
    "target_table":     "bronze.meta_facebook_ad_insights",
    "params": {
        "date_preset":  "last_7d",
        "since":        "2026-05-01",
        "until":        "2026-05-13"
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
    "records": [
        {"ad_id": "x1", "impressions": "1234", "spend": "12.50", "date_start": "2026-05-13"}
    ],
    "meta": {
        "account":          "act_1234567890",
        "total_campaigns":  3,
        "total_adsets":     17,
        "total_ads":        128,
        "response_subkey":  "ads",
        "bq_table_id":      "monks-mds-dev.bronze.meta_facebook_ad_insights",
        "rows_written":     128,
        "schema_created":   false,
        "tenant_id":        "cliente1",
        "manifest_id":      "meta_facebook_ad_insights"
    },
    "errors": []
}
```

When the selected level exceeds `RECORDS_PREVIEW_CAP` (200), `records`
holds the first 200 rows only and `meta.records_preview_capped_at`
is set. The complete data set is in BigQuery.

### Error responses

| HTTP | `code`                    | Meaning                                                |
|-----:|---------------------------|--------------------------------------------------------|
|  400 | `MISSING_TENANT_ID`       | body.tenant_id missing or not a string                 |
|  400 | `MISSING_MANIFEST_ID`     | body.manifest_id missing or not a string               |
|  400 | `MANIFEST_MISMATCH`       | this CF only handles `meta_facebook_ad_insights`       |
|  400 | `INVALID_PARAMS`          | body.params not an object                              |
|  400 | `INVALID_TARGET_TABLE`    | target_table not `dataset.table` / `proj.ds.table`     |
|  400 | `MISSING_ACCOUNT_ID`      | connector signalled missing ad_account_id (rare — SM)  |
|  400 | `INVALID_PARAMS`          | connector rejected params shape                        |
|  401 | `UNAUTHORIZED`            | Meta returned 401 (expired/invalid token)              |
|  401 | `MISSING_CREDENTIALS`     | no access_token resolved                               |
|  403 | `FORBIDDEN`               | Meta returned 403 (ad account permission)              |
|  500 | `MISSING_SECRET`          | Secret Manager call failed                             |
|  500 | `CONNECTOR_NOT_PACKAGED`  | `facebook_ads` import failed inside CF                 |
|  500 | `CONNECTOR_RAISED`        | connector raised an unexpected exception               |
|  500 | `UNEXPECTED_ERROR`        | connector reported an unspecified internal failure     |
|  500 | `BQ_WRITE_FAILED`         | BigQuery load job failed                               |

## Operational notes

- **Cold start**: ~3-5s including google-cloud-bigquery +
  google-cloud-secret-manager initialisation. Both clients are
  lazy-imported inside the helpers, so cold starts that hit
  `MISSING_SECRET` don't pay the BQ import cost.
- **Auth model**: Meta uses an access_token (System User), not a
  service account. The connector talks to the Graph API over plain
  HTTPS via `requests`. No google-auth needed inside the CF — that's
  why this CF's `requirements.txt` omits the `google-auth` pin that
  `dv360-fetch` carries.
- **Multi-level response**: Meta's Insights endpoint returns rows at
  ad-level by default, but the connector groups them up into
  `{campaigns, adsets, ads}`. Today we write the `ads` level to the
  bronze table because it carries the full join key (`campaign_id`,
  `adset_id`, `ad_id`). Switch `manifest.metadata.response_subkey` to
  `"campaigns"` or `"adsets"` to ship a higher level instead.
- **Concurrency**: defaults to `max-instances=5`. Each instance is a
  single Python process; gen2 supports `--concurrency` if we ever need
  to batch.
- **Timeout**: 540s. Meta Insights typically finishes <30s for a 7-day
  pull at ad-level on a single ad account, but historical pulls with
  breakdowns can paginate for longer. The MDS backend uses
  `limits.max_call_duration_seconds + 20s` as its client-side timeout
  (`HTTPBackend._resolve_timeout`).
- **Logs**: structured logs land in Cloud Logging. Search by
  `resource.labels.function_name="meta-facebook-insights"`. The most
  useful filters are `severity>=ERROR` (errors) and
  `jsonPayload.tenant_id="<id>"` (per-tenant trace).

## Related code

- `src/ingestion/dispatcher/http.py` — HTTPBackend (caller side).
- `connectors-library/meta/facebook/facebook_ads.py` — the actual
  connector (`fetch()` entry point).
- `connectors-library/meta/facebook/manifest.json` — SSoT for fields,
  secret names, endpoint definition, `response_subkey`.
- `cloud-functions/dv360-fetch/` — sibling CF for DV360, same shape.
- `docs/mvp-phase5-checklist.md` — Fase 5 MVP task tracker.
- `docs/architecture.md` — Secret Manager naming convention + IAM model.
