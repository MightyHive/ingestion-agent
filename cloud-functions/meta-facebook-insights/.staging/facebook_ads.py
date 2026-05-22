"""
Facebook Ads — Marketing API connector.

Fetches performance insights at three levels:
    - Campaigns
    - Ad Sets
    - Ads

All numeric fields returned by Meta arrive as strings and are cast to float here.

pass ``params["fields"]`` as a list of insight field names. Empty or omitted list = all
fields available for the reporting ``level`` (``campaign`` / ``adset`` / ``ad``).
The connector intersects your list with the allowed set for that level so the
request does not 400. Invalid-only requests fall back to a minimal set.

API reference:
    https://developers.facebook.com/docs/marketing-api/insights
    Base URL: https://graph.facebook.com/v23.0/
"""

import logging
import json
from datetime import datetime, timedelta, timezone
import os
from typing import Any
from api_handler import ApiHandler, ForbiddenException, UnauthorizedException



BASE_URL = "https://graph.facebook.com/v23.0"

# Per-level insight fields for /insights ``fields=`` (also returned as columns in rows).
# ``date_start`` / ``date_stop`` are always in the response for time_increment queries.
# Do not use ``country`` / ``user_segment_key`` as generic fields (breakdowns / restricted).
# See: https://developers.facebook.com/docs/marketing-api/insights/fields
_SHARED_METRICS: list[str] = [
    "impressions",
    "full_view_impressions",
    "full_view_reach",
    "reach",
    "spend",
    "clicks",
    "frequency",
    "cpm",
    "cpc",
    "cpp",
    "ctr",
    "video_p25_watched_actions",
    "video_p50_watched_actions",
    "video_p75_watched_actions",
    "video_p100_watched_actions",
    "video_play_actions",
    "actions",
    "conversions",
]
_CAMPAIGN_OBJECT: list[str] = [
    "account_id",
    "account_name",
    "campaign_id",
    "campaign_name",
    "created_time",
    "objective",
]
_ADSET_OBJECT: list[str] = [
    "adset_id",
    "adset_name",
]
_AD_OBJECT: list[str] = [
    "ad_id",
    "ad_name",
    "ad_click_actions",
]
# Allowed ``fields=`` for each level (union of object dim + shared metrics for that object).
AVAILABLE_FIELDS: dict[str, list[str]] = {
    "campaign": _CAMPAIGN_OBJECT + _SHARED_METRICS,
    "adset": _CAMPAIGN_OBJECT + _ADSET_OBJECT + _SHARED_METRICS,
    "ad": _CAMPAIGN_OBJECT + _ADSET_OBJECT + _AD_OBJECT + _SHARED_METRICS,
}
# Back-compat: copy of the full ad-level set (safe if callers mutate FIELDS).
FIELDS: list[str] = list(AVAILABLE_FIELDS["ad"])

# Numeric fields to cast from string → float
NUMERIC_FIELDS = {
    "impressions", "full_view_impressions",  "full_view_reach",
    "reach", "spend", "clicks", "frequency", "cpm", "cpc",
    "cpp", "ctr", "video_p25_watched_actions", "video_p50_watched_actions",
    "video_p75_watched_actions", "video_p100_watched_actions", "video_play_actions"
}

# Action types we want to extract from the `actions` array
ACTION_ATTRIBUTION_WINDOW = {
"1d_view", "7d_view", "28d_view", "1d_click", "7d_click", "28d_click"
} #default ["7d_click","1d_view"]


def _get_safe_insight_fields(level: str, requested: list[str] | None) -> list[str]:
    """
    Intersect caller-requested fields with the allow-list for the insights ``level``.

    If ``requested`` is None or empty, return all available fields for that level.
    If the intersection is empty, fall back to a minimal set that is valid for that level.
    """
    available = AVAILABLE_FIELDS.get(level) or AVAILABLE_FIELDS["ad"]
    if not requested:
        return list(available)
    safe = [f for f in requested if f in available]
    if not safe:
        logging.warning(
            f"None of the requested fields are valid for level {level!r}. "
            f"Falling back to a minimal set."
        )
        if level == "campaign":
            return ["account_id", "campaign_id", "campaign_name", "impressions", "spend", "clicks", "actions"]
        if level == "adset":
            return [
                "account_id", "campaign_id", "adset_id", "adset_name",
                "impressions", "spend", "clicks", "actions",
            ]
        return [
            "account_id", "campaign_id", "adset_id", "ad_id", "ad_name",
            "impressions", "spend", "clicks", "actions",
        ]
    return safe


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _cast_numeric(record: dict) -> dict:
    """Cast known numeric fields from string to float. Skips if not present."""
    for field in NUMERIC_FIELDS:
        if field in record:
            try:
                record[field] = float(record[field])
            except (ValueError, TypeError):
                record[field] = None
    return record



class FacebookAds(ApiHandler):
    """
    Connector for the Meta Marketing API.

    Args:
        access_token (str): Meta System User Token with ads_read + read_insights.
        ad_account_id (str): Ad account ID, e.g. "act_123456789".
        days_back (int): How many days of data to fetch (default 14).
        timeout (int): HTTP timeout in seconds.
        max_retries (int): Retry attempts on transient errors.
    """

    def __init__(
        self,
        access_token: str,
        ad_account_id: str,
        days_back: int = 14,
        timeout: int = 60,
        max_retries: int = 3,
    ):
        super().__init__(
            access_token=access_token,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=2.0,
        )
        self._base_url = BASE_URL

        # Normalise account ID — API requires "act_" prefix
        if not ad_account_id.startswith("act_"):
            ad_account_id = f"act_{ad_account_id}"
        self.ad_account_id = ad_account_id
        self.days_back = days_back


    def _date_range(self, days_back: int = None, date_start: str = None, date_stop: str = None) -> dict:
        """Return since/until dict for the time_range parameter."""
        if date_start and date_stop:
            return {"since": date_start, "until":date_stop}
        n = days_back if days_back is not None else self.days_back
        today = datetime.now().date()
        since = (today - timedelta(days=n)).strftime("%Y-%m-%d")
        until = today.strftime("%Y-%m-%d")
        return {"since": since, "until": until}


    def _paginate(self, path: str, params: dict) -> list:
        """
        Cursor-based pagination for Meta Graph API.
        Iterates paging.cursors.after until paging.next is absent.
        """
        all_data = []
        url = None  # first call uses path + params; subsequent calls use next URL

        while True:
            if url:
                response = self.request(path="", _url=url)
            else:
                response = self.request(path=path, params=params)

            data = response.get("data", [])
            all_data.extend(data)

            paging = response.get("paging", {})
            next_url = paging.get("next")
            if not next_url:
                break
            url = next_url

        return all_data


    def _fetch_insights(self, level: str, fields: list, days_back: int = None, date_start: str = None, date_stop: str = None) -> list:
        """
        Call /{account_id}/insights with breakdown by day at the given level.

        Args:
            level:    "campaign" | "adset" | "ad"
            fields:   list of field names to request
            days_back: override instance default

        Returns:
            List of dicts, one per (level entity, day).
        """
        time_range = self._date_range(days_back, date_start, date_stop)

        params = {
            "level": level,
            "fields": ",".join(fields),
            "time_increment": 1,          # daily breakdown
            "time_range": json.dumps(time_range, separators=(',', ':')),  # JSON-like string
            "limit": 500, 
            #"action_attribution_window": '["7d_click", "1d_view"]'
        }

        logging.info(
            f"Fetching {level} insights | account={self.ad_account_id} | "
            f"range={time_range['since']} → {time_range['until']}"
        )

        raw_rows = self._paginate(
            path=f"{self.ad_account_id}/insights",
            params=params,
        )

        results = []
        for row in raw_rows:
            row = _cast_numeric(row)
            results.append(row)

        logging.info(f"  → {len(results)} rows fetched at {level} level")
        return results



    def get_campaign_insights(
        self,
        days_back: int = None,
        date_start: str = None,
        date_stop: str = None,
        requested_fields: list[str] | None = None,
    ) -> list:
        """
        Fetch daily performance metrics at campaign level.

        """
        fields = _get_safe_insight_fields("campaign", requested_fields)
        return self._fetch_insights(
            level="campaign",
            fields=fields,
            days_back=days_back,
            date_start=date_start,
            date_stop=date_stop,
        )

    def get_adset_insights(
        self,
        days_back: int = None,
        date_start: str = None,
        date_stop: str = None,
        requested_fields: list[str] | None = None,
    ) -> list:
        """
        Fetch daily performance metrics at ad set level.

        Returns:
            List of dicts with adset_id, adset_name, campaign_id,
            plus the same performance fields as campaigns.
        """
        fields = _get_safe_insight_fields("adset", requested_fields)
        return self._fetch_insights(
            level="adset",
            fields=fields,
            days_back=days_back,
            date_start=date_start,
            date_stop=date_stop,
        )

    def get_ad_insights(
        self,
        days_back: int = None,
        date_start: str = None,
        date_stop: str = None,
        requested_fields: list[str] | None = None,
    ) -> list:
        """
        Fetch daily performance metrics at ad level, including
        video quartiles and flattened action_type conversions.

        Returns:
            List of dicts with ad_id, ad_name, adset_id, campaign_id,
            video metrics, and per-type action counts.
        """
        fields = _get_safe_insight_fields("ad", requested_fields)
        return self._fetch_insights(
            level="ad",
            fields=fields,
            days_back=days_back,
            date_start=date_start,
            date_stop=date_stop,
        )

    def fetch_all(
        self,
        days_back: int = None,
        date_start: str = None,
        date_stop: str = None,
        requested_fields: list[str] | None = None,
    ) -> dict:
        """
        Convenience method: fetch all three levels in one call.

        ``requested_fields`` is filtered separately per level; ad-only fields
        (e.g. ad_id) are dropped at campaign/ad set levels automatically.

        Returns:
            {
                "campaigns": [...],
                "adsets":    [...],
                "ads":       [...]
            }
        """
        return {
            "campaigns": self.get_campaign_insights(
                days_back=days_back, date_start=date_start, date_stop=date_stop, requested_fields=requested_fields
            ),
            "adsets": self.get_adset_insights(
                days_back=days_back, date_start=date_start, date_stop=date_stop, requested_fields=requested_fields
            ),
            "ads": self.get_ad_insights(
                days_back=days_back, date_start=date_start, date_stop=date_stop, requested_fields=requested_fields
            ),
        }

def fetch(params: dict, context: dict) -> dict:
    """
    Entry point for the Facebook Ads connector.

    Args:
        params (dict): Runtime parameters.
            days_back  (int): Days of history to fetch. Default: 14.
            date_start (str): ISO date e.g. '2024-01-01'. Overrides days_back.
            date_stop  (str): ISO date e.g. '2024-01-31'. Overrides days_back.
            since      (str): Same as date_start (alias, matches Instagram pattern).
            until      (str): Same as date_stop (alias, matches Instagram pattern).
            fields     (list[str]): Field names to request. Empty = all available per level.
        context (dict): Execution context.
            ad_account_id (str): REQUIRED. e.g. "act_123456789".
            access_token  (str): Optional. Overrides META_ACCESS_TOKEN env var.

    Returns:
        dict with:
            status   (str):  "OK" | "ERR"
            code     (str):  Machine-readable status code.
            records  (dict): {"campaigns": [...], "adsets": [...], "ads": [...]}
            meta     (dict): Execution metadata.
            errors   (list): Non-fatal warnings.
    """
    # --- Validar contexto ---
    ad_account_id = context.get("ad_account_id")
    if not ad_account_id:
        return {
            "status": "ERR",
            "code": "MISSING_ACCOUNT_ID",
            "records": {},
            "meta": {},
            "errors": ["context.ad_account_id is required"],
        }

    access_token = context.get("access_token") or os.getenv("META_ACCESS_TOKEN")
    if not access_token:
        return {
            "status": "ERR",
            "code": "MISSING_CREDENTIALS",
            "records": {},
            "meta": {},
            "errors": ["No access token. Set context.access_token or META_ACCESS_TOKEN env var."],
        }

    # --- Parámetros ---
    days_back  = int(params.get("days_back", 14))
    date_start = params.get("date_start") or params.get("since")
    date_stop  = params.get("date_stop") or params.get("until")
    fields: list[str] = params.get("fields") or []

    # --- Fetch ---
    try:
        api = FacebookAds(access_token=access_token, ad_account_id=ad_account_id)
        records = api.fetch_all(
            days_back=days_back,
            date_start=date_start,
            date_stop=date_stop,
            requested_fields=fields or None,
        )
        return {
            "status": "OK",
            "code": "FETCH_OK",
            "records": records,
            "meta": {
                "ad_account_id": ad_account_id,
                "date_start": date_start,
                "date_stop": date_stop,
                "days_back": days_back,
                "fields_requested": fields or "all",
                "total_campaigns": len(records["campaigns"]),
                "total_adsets": len(records["adsets"]),
                "total_ads": len(records["ads"]),
            },
            "errors": [],
        }
    except UnauthorizedException as e:
        return {"status": "ERR", "code": "UNAUTHORIZED",      "records": {}, "meta": {}, "errors": [str(e)]}
    except ForbiddenException as e:
        return {"status": "ERR", "code": "FORBIDDEN",         "records": {}, "meta": {}, "errors": [str(e)]}
    except Exception as e:
        logging.error(f"Unexpected error in fetch: {e}")
        return {"status": "ERR", "code": "UNEXPECTED_ERROR",  "records": {}, "meta": {}, "errors": [str(e)]}