#!/usr/bin/env bash
# deploy.sh — stage + deploy the meta-facebook-insights Cloud Function.
#
# The connector source (facebook_ads.py + api_handler.py + manifest.json)
# lives under connectors-library/meta/facebook/ and is shared with the
# legacy stack. We DO NOT want to fork the connector into the CF dir
# permanently, so this script copies it in just-in-time, runs the
# deploy, and (optionally) cleans up.
#
# Pattern is identical to cloud-functions/dv360-fetch/deploy.sh — kept
# verbatim where possible so future "B4-X" CFs stay symmetric.
#
# Usage:
#   ./deploy.sh stage              # vendor connector + manifest into ./.staging
#   ./deploy.sh deploy             # stage + gcloud functions deploy
#   ./deploy.sh smoke              # stage + run functions-framework locally on :8080
#   ./deploy.sh clean              # remove .staging
#
# Required gcloud config (already set in B0 / B1):
#   gcloud config set project monks-mds-dev
#   gcloud auth application-default login
#
# Required env (override via shell):
#   CF_NAME      = meta-facebook-insights        (matches manifest.endpoint.cloud_function_name)
#   CF_REGION    = us-central1                   (matches manifest.endpoint.cloud_function_region)
#   CF_RUNTIME   = python311
#   CF_SA        = mds-cf-runner@monks-mds-dev.iam.gserviceaccount.com
#   CF_PROJECT   = monks-mds-dev
#   CF_MEMORY    = 1Gi
#   CF_TIMEOUT   = 540s                          (Meta insights can paginate; CF gen2 max is 60m)
#   CF_MAX_INSTANCES = 5

set -euo pipefail

# --- Paths --------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CONNECTOR_DIR="${REPO_ROOT}/connectors-library/meta/facebook"
MANIFEST_SRC="${CONNECTOR_DIR}/manifest.json"
STAGING_DIR="${SCRIPT_DIR}/.staging"

# --- Config (env-overridable) -------------------------------------------
: "${CF_NAME:=meta-facebook-insights}"
: "${CF_REGION:=us-central1}"
: "${CF_RUNTIME:=python311}"
: "${CF_PROJECT:=monks-mds-dev}"
: "${CF_SA:=mds-cf-runner@${CF_PROJECT}.iam.gserviceaccount.com}"
: "${CF_MEMORY:=1Gi}"
: "${CF_TIMEOUT:=540s}"
: "${CF_MAX_INSTANCES:=5}"

# --- Helpers ------------------------------------------------------------
log()  { printf '[deploy.sh] %s\n' "$*" >&2; }
fail() { log "ERROR: $*"; exit 1; }

ensure_src_present() {
    [[ -f "${CONNECTOR_DIR}/facebook_ads.py" ]] || \
        fail "connector source not found at ${CONNECTOR_DIR}/facebook_ads.py"
    [[ -f "${CONNECTOR_DIR}/api_handler.py" ]] || \
        fail "api_handler.py not found at ${CONNECTOR_DIR}/api_handler.py"
    [[ -f "${MANIFEST_SRC}" ]] || \
        fail "manifest.json not found at ${MANIFEST_SRC}"
}

# stage: build a self-contained dir at .staging/ with everything the
# CF needs. We copy instead of symlink because `gcloud functions deploy`
# follows the source tree and doesn't always do the right thing with
# symlinks to outside the source dir.
cmd_stage() {
    ensure_src_present
    log "Staging into ${STAGING_DIR}"
    rm -rf "${STAGING_DIR}"
    mkdir -p "${STAGING_DIR}"

    cp "${SCRIPT_DIR}/main.py"          "${STAGING_DIR}/main.py"
    cp "${SCRIPT_DIR}/requirements.txt" "${STAGING_DIR}/requirements.txt"
    cp "${SCRIPT_DIR}/.gcloudignore"    "${STAGING_DIR}/.gcloudignore"

    cp "${CONNECTOR_DIR}/facebook_ads.py" "${STAGING_DIR}/facebook_ads.py"
    cp "${CONNECTOR_DIR}/api_handler.py"  "${STAGING_DIR}/api_handler.py"
    cp "${MANIFEST_SRC}"                  "${STAGING_DIR}/manifest.json"

    touch "${STAGING_DIR}/staged.lock"
    log "Staging complete:"
    ls -la "${STAGING_DIR}" >&2
}

# deploy: stage then `gcloud functions deploy`. The CF is private
# (--no-allow-unauthenticated) — the MDS backend authenticates with a
# Google-signed id_token whose audience equals the CF URL.
cmd_deploy() {
    cmd_stage
    log "Deploying ${CF_NAME} to project=${CF_PROJECT}, region=${CF_REGION}"
    gcloud functions deploy "${CF_NAME}" \
        --gen2 \
        --project="${CF_PROJECT}" \
        --region="${CF_REGION}" \
        --runtime="${CF_RUNTIME}" \
        --source="${STAGING_DIR}" \
        --entry-point=run \
        --trigger-http \
        --no-allow-unauthenticated \
        --service-account="${CF_SA}" \
        --memory="${CF_MEMORY}" \
        --timeout="${CF_TIMEOUT}" \
        --max-instances="${CF_MAX_INSTANCES}" \
        --set-env-vars="GCP_PROJECT=${CF_PROJECT}"
    log "Deploy complete. URL:"
    gcloud functions describe "${CF_NAME}" \
        --gen2 --region="${CF_REGION}" --project="${CF_PROJECT}" \
        --format="value(serviceConfig.uri)"
}

# smoke: run the CF locally via functions-framework so we can hit
# http://localhost:8080 from the MDS backend in auto/http mode.
cmd_smoke() {
    cmd_stage
    log "Starting functions-framework on http://localhost:8080"
    log "Backend should set MDS_CF_BASE_URL=http://localhost:8080 MDS_RUNTIME=http"
    cd "${STAGING_DIR}"
    # Activate the local venv if one exists, otherwise rely on PATH.
    if [[ -f "${SCRIPT_DIR}/.venv/bin/activate" ]]; then
        # shellcheck disable=SC1090
        source "${SCRIPT_DIR}/.venv/bin/activate"
    fi
    pip install -q -r requirements.txt
    exec functions-framework --target=run --port=8080 --debug
}

cmd_clean() {
    log "Removing ${STAGING_DIR}"
    rm -rf "${STAGING_DIR}"
}

# --- Dispatch -----------------------------------------------------------
case "${1:-}" in
    stage)  cmd_stage ;;
    deploy) cmd_deploy ;;
    smoke)  cmd_smoke ;;
    clean)  cmd_clean ;;
    "" | help | -h | --help)
        cat <<EOF
deploy.sh — stage + deploy the meta-facebook-insights Cloud Function

Subcommands:
  stage    Vendor connector + manifest into .staging/
  deploy   stage + gcloud functions deploy (private gen2 HTTP)
  smoke    stage + run functions-framework locally on :8080
  clean    remove .staging/

Env overrides:
  CF_NAME, CF_REGION, CF_RUNTIME, CF_PROJECT, CF_SA, CF_MEMORY,
  CF_TIMEOUT, CF_MAX_INSTANCES

Current defaults:
  CF_NAME=${CF_NAME}
  CF_REGION=${CF_REGION}
  CF_RUNTIME=${CF_RUNTIME}
  CF_PROJECT=${CF_PROJECT}
  CF_SA=${CF_SA}
  CF_MEMORY=${CF_MEMORY}
  CF_TIMEOUT=${CF_TIMEOUT}
  CF_MAX_INSTANCES=${CF_MAX_INSTANCES}
EOF
        ;;
    *) fail "unknown subcommand: $1 (try 'help')" ;;
esac
