"""tiktok_marketing connector — TikTok Marketing API.

Auto-scaffolded from API research.
Pagination: offset/limit (max 1000 per page)
Rate limit: unspecified; refer to TikTok API documentation

Bronze DDL (persisted from Data Architect):
CREATE TABLE IF NOT EXISTS `general-motors-global.raw_tiktok.tiktok_performance_raw`
(
  impressions FLOAT64 NULLABLE OPTIONS(description=''),
  spend FLOAT64 NULLABLE OPTIONS(description='This value is provided in the account\'s currency and is already in decimal format.'),
  ingest_ts TIMESTAMP REQUIRED OPTIONS(description='UTC timestamp when this row was loaded into BigQuery.')
)
PARTITION BY DATE(ingest_ts)
OPTIONS(
  description='Bronze landing table for TikTok Marketing API — immutable raw capture.',
  labels=[('layer', 'raw'), ('platform', 'tiktok')]
);
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

    tiktok_access_token = os.getenv("TIKTOK_ACCESS_TOKEN")
    if not tiktok_access_token:
        return {
            "status": "ERR",
            "code": "MISSING_CREDENTIALS",
            "records": [],
            "errors": ["Missing required env vars: TIKTOK_ACCESS_TOKEN"],
        }

    headers = {
        "Authorization": f"Bearer {tiktok_access_token}",
    }
    query = {
        "fields": ",".join(requested_fields),
    }
    cursor = params.get("cursor")
    if cursor:
        query["cursor"] = cursor

    url = "https://business-api.tiktok.com/open_api/v1.3/report/integrated/get/"
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
        page_info = body.get("page_info", body.get("paging", {}))
        if isinstance(page_info, dict) and page_info.get("has_more", False):
            next_cursor = str(int(params.get("cursor", "1")) + 1)
    return {
        "status": "OK",
        "code": "FETCH_OK",
        "records": records if isinstance(records, list) else [],
        "next_cursor": next_cursor,
        "meta": {"requested_fields": requested_fields},
        "errors": [],
    }
