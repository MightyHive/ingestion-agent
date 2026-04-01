
"""meta_marketing_performance connector — Meta Marketing API.

Auto-scaffolded from API research.
Pagination: cursor-based (paging.after)
Auth: OAuth2 Bearer Token

Bronze DDL (persisted from Data Architect):
CREATE TABLE IF NOT EXISTS `general-motors-global.raw_meta_marketing.meta_performance_raw`
(
  campaign_name STRING NULLABLE OPTIONS(description='None'),
  campaign_id STRING NULLABLE OPTIONS(description='Always STRING, even though it looks like an int'),
  video_30_sec_watched_default_uas FLOAT64 NULLABLE OPTIONS(description='API returns STRING — cast to numeric'),
  spend FLOAT64 NULLABLE OPTIONS(description='API returns STRING — cast to float'),
  impressions FLOAT64 NULLABLE OPTIONS(description='API returns STRING — cast to numeric'),
  ingest_ts TIMESTAMP REQUIRED OPTIONS(description='UTC timestamp when this row was loaded into BigQuery.')
)
PARTITION BY DATE(ingest_ts)
OPTIONS(
  description='Bronze landing table for Meta Marketing API — immutable raw capture.',
  labels=[('layer', 'raw'), ('platform', 'meta')]
);

API SPECIFICATIONS (persisted contract):
  Base URL: https://graph.facebook.com/v21.0/
  Auth type: OAuth2 Bearer Token
  Pagination: cursor-based (paging.after)
  HTTP method: GET
  Headers required: (none beyond auth)
"""

from __future__ import annotations

import os
from typing import Any

import requests


DEFAULT_FIELDS = ['id']


def fetch(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    requested_fields = params.get("fields", DEFAULT_FIELDS)
    if not isinstance(requested_fields, list) or not requested_fields:
        return {
            "status": "ERR",
            "code": "FIELDS_REQUIRED",
            "records": [],
            "errors": ["params.fields must be a non-empty list"],
        }

    meta_access_token = os.getenv("META_ACCESS_TOKEN")
    if not meta_access_token:
        return {
            "status": "ERR",
            "code": "MISSING_CREDENTIALS",
            "records": [],
            "errors": ["Missing required env vars: META_ACCESS_TOKEN"],
        }

    headers = {
        "Authorization": f"Bearer {meta_access_token}",
    }
    query = {
        "fields": ",".join(requested_fields),
    }
    cursor = params.get("cursor")
    if cursor is not None and str(cursor).strip() != "":
        if "after" in 'cursor-based (paging.after)':
            query["after"] = str(cursor)
        else:
            query["cursor"] = str(cursor)

    root = 'https://graph.facebook.com/v21.0/'
    path_tpl = '/{account_id}/insights'
    subs: dict[str, Any] = {**context, **params}
    path = path_tpl
    for key in sorted(subs.keys(), key=lambda k: len(str(k)), reverse=True):
        if isinstance(key, str):
            token = "{" + key + "}"
            if token in path:
                val = subs.get(key)
                path = path.replace(token, "" if val is None else str(val))
    if not root:
        return {
            "status": "ERR",
            "code": "MISSING_BASE_URL",
            "records": [],
            "errors": [
                "Set api_spec.base_url (persisted) or context.base_url; "
                "reporting_endpoint was a relative path template."
            ],
        }
    url = f"{root.rstrip('/')}/{path.lstrip('/')}" if path else root

    if not url:
        return {
            "status": "ERR",
            "code": "MISSING_URL",
            "records": [],
            "errors": ["No request URL: set reporting_endpoint or context.base_url."],
        }

    response = requests.get(url, headers=headers, params=query, timeout=60)
    if response.status_code >= 400:
        return {
            "status": "ERR",
            "code": "UPSTREAM_HTTP_ERROR",
            "records": [],
            "errors": [f"HTTP {response.status_code}: {response.text[:300]}"],
        }

    body = response.json()
    records = body.get("data", []) if isinstance(body, dict) else []
    next_cursor = None
    if isinstance(body, dict):
        paging = body.get("paging", {})
        cursors = paging.get("cursors", {}) if isinstance(paging, dict) else {}
        next_cursor = cursors.get("after") or body.get("next_cursor")
    return {
        "status": "OK",
        "code": "FETCH_OK",
        "records": records if isinstance(records, list) else [],
        "next_cursor": next_cursor,
        "meta": {"requested_fields": requested_fields},
        "errors": [],
    }
