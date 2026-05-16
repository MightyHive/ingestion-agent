#!/usr/bin/env bash
# Start the ingestion API with config/tenants.json wired for local dev.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export MDS_TENANTS_FILE="${MDS_TENANTS_FILE:-$ROOT/config/tenants.json}"
export RUN_MODE=api
cd "$ROOT/src"
echo "MDS_TENANTS_FILE=$MDS_TENANTS_FILE"
exec uvicorn api:app --reload --host 0.0.0.0 --port 8000
