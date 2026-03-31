from __future__ import annotations

import os
from typing import Any

import requests

DEFAULT_FIELDS = ['id', 'likes', 'date']

def fetch(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    requested_fields = params.get("fields", DEFAULT_FIELDS)
    if not isinstance(requested_fields, list) or not requested_fields:
        return {
            "status": "ERR",
            "code": "FIELDS_REQUIRED",
            "records": [],
            "errors": ["params.fields must be a non-empty list"],
        }

    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        return {
            "status": "ERR",
            "code": "MISSING_API_KEY",
            "records": [],
            "errors": ["Missing required API key environment variable"],
        }

    headers = {
        "Authorization": f"Bearer {api_key}" if "bearer_token" else api_key,
    }
    query = {
        "fields": ",".join(requested_fields),
    }
    cursor = params.get("cursor")
    if cursor:
        query["cursor"] = cursor

    url = "/" if "" and "" else ""
    response = requests.get(url, headers=headers, params=query, timeout=30)
    if response.status_code >= 400:
        return {
            "status": "ERR",
            "code": "UPSTREAM_HTTP_ERROR",
            "records": [],
            "errors": [f"HTTP {response.status_code}: {response.text[:300]}"]
        }

    payload = response.json()
    records = payload.get("data", []) if isinstance(payload, dict) else []
    next_cursor = payload.get("next_cursor") if isinstance(payload, dict) else None
    return {
        "status": "OK",
        "code": "FETCH_OK",
        "records": records if isinstance(records, list) else [],
        "next_cursor": next_cursor,
        "meta": {"requested_fields": requested_fields},
        "errors": [],
    }
