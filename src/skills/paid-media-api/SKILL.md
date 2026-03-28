---
name: paid-media-api
description: "API Investigator Agent (Data Sourcer). Specializes in researching external API documentation and extracting everything needed to build a read-only data pipeline: endpoints, authentication flows (OAuth, Bearer tokens, API keys), rate limits, pagination patterns, and raw JSON response schemas. Covers Meta Marketing API, Google Ads API, YouTube Data API, and TikTok Marketing API, but also handles unknown or custom APIs via search_web, read_documentation_url, and analyze_json_schema. Always trigger this skill before writing any code or proposing any schema. This agent NEVER writes, creates, or modifies campaigns — read-only extraction only."
---

# Paid Media API Skill — Read-Only Data Extraction

Extracts the minimum information needed for a downstream Data Modeler to define a BigQuery RAW schema.
Scope: **authentication**, **reporting endpoints**, **available fields**, **pagination**, **rate limits**.
Never generates code to create, update, or delete campaigns or ads.

---

## Execution Flow

```
START → receive api_name
  ↓
Is api_name in KNOWN PLATFORMS list?
  │
  ├── YES → 1. Load reference file for that platform
  │          2. freshness_check: read_documentation_url(docs_url)
  │             → compare against reference file
  │             → if changes detected: flag delta to Coordinator
  │          3. Go to → EXTRACT FIELDS
  │
  └── NO  → 1. search_web("{api_name} official API documentation")
             2. read_documentation_url(top result)
                → extract: base_url, auth_method, reporting_endpoint,
                  available_fields, pagination, rate_limits
             3. analyze_json_schema(sample_response) → infer field types
             4. Go to → EXTRACT FIELDS

EXTRACT FIELDS
  → identify which fields map to:
    impressions, clicks, spend, ctr, conversions,
    video_views, reach, date, campaign_name, platform_id
  → Go to → OUTPUT

OUTPUT → return Investigation Report (see format below)
```

---

## Known Platforms

| Platform | Docs URL | Auth | Reference file |
|---|---|---|---|
| Meta Marketing API | https://developers.facebook.com/docs/marketing-apis/ | OAuth 2.0 (v21.0) | `references/meta.md` |
| Google Ads API | https://developers.google.com/google-ads/api/docs/start | Service Account via google-ads.yaml | `references/google-ads.md` |
| TikTok Marketing API | https://business-api.tiktok.com/portal/docs | OAuth 2.0 (v1.3) | `references/tiktok.md` |

For unknown APIs: run the full investigation flow, then save findings as a new file in `references/`.

---

## 🔐 AUTHENTICATION

### Meta
```
Base URL: https://graph.facebook.com/v21.0/
Auth:     OAuth 2.0
Token:    System User Token (non-expiring) — recommended for server-to-server
Permissions needed (read-only): ads_read, read_insights
```

### Google Ads
```
Auth:     Service Account via google-ads.yaml
Required: developer_token, login_customer_id, json_key_file_path
SDK:      google-ads==29.2.0 (Python)

⚠️ Google Ads has NO traditional REST API.
   All data fetched via Python SDK: ga_service.search_stream()
   Never called directly via curl or requests.
```

### TikTok
```
Base URL: https://business-api.tiktok.com/open_api/v1.3/
Auth:     OAuth 2.0
Header:   Access-Token: {access_token}
advertiser_id: passed as query param, NOT in URL path
```

---

## 📡 REPORTING ENDPOINTS (read-only)

### Meta — Performance

```
Endpoint: GET /{account_id}/insights
Level:    campaign + ad
Lookback: 7 days rolling
Granularity: date_start (day)

Key fields:
  impressions, link_click_default_uas (clicks), spend, reach,
  video_p25/50/75/100_watched_default_uas, video_30_sec_watched_default_uas

⚠️ ALL numeric fields arrive as STRINGS from the API — always cast before loading to BQ.
```

### Google Ads — Performance

```
Method:   ga_service.search_stream(customer_id, query)
Resource: ad_group_ad with metrics.* and segments.date
Lookback: 7 days rolling
Granularity: segments.date (required for daily rows)

Example GAQL:
  SELECT campaign.id, ad_group_ad.ad.id, segments.date,
    metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.ctr,
    metrics.video_views, metrics.video_quartile_p25_rate,
    metrics.video_quartile_p100_rate
  FROM ad_group_ad
  WHERE segments.date DURING LAST_7_DAYS

⚠️ cost_micros: always divide by 1,000,000 — never store raw micros in BQ.
⚠️ video_quartile_p*_rate: these are RATES (0.0–1.0), not counts.
⚠️ IDs (campaign, ad group, ad) are returned as int64 — cast to STRING.
⚠️ Without segments.date, metrics aggregate across the full date range.
```

### TikTok — Performance

```
Endpoint: GET /report/integrated/get/
report_type: BASIC
Lookback: 7 days rolling
Granularity: stat_time_day

Request params:
  advertiser_id (query param), report_type, dimensions, metrics, start_date, end_date, page_size

Key metrics:
  spend, impressions, clicks, reach, ctr, cpc, cpm,
  video_play_actions, video_watched_2s/6s,
  video_views_p25/50/75/100

⚠️ spend is already in currency units (NOT micros) — do NOT divide.
⚠️ ctr is a PERCENTAGE (5.2 = 5.2%), not a ratio — normalize for cross-platform.
⚠️ video_views_p* are ABSOLUTE COUNTS (opposite of Google Ads rates).
⚠️ stat_time_day includes time component (YYYY-MM-DD HH:MM:SS) — truncate to date.
⚠️ Max date range per request: 30 days — chunk for historical backfills.
```

---

## ⚡ RATE LIMITS

| Platform | Limit | Notes |
|---|---|---|
| Meta | cursor-based pagination | iterate `after` cursor until `next` is absent |
| Google Ads | ~15,000 queries/day | use `search_stream` — handles pagination automatically |
| TikTok | 10 req/sec · 60 req/min (reporting) | max 30-day range; max page_size 1,000 |

---

## 🚨 CROSS-PLATFORM GOTCHAS

| Issue | Meta | Google Ads | TikTok |
|---|---|---|---|
| Numeric fields as strings | ✅ Yes — cast everything | ❌ Native types | ❌ Mostly native |
| Spend unit | Float (currency) | **Micros ÷ 1,000,000** | Float (currency, NOT micros) |
| CTR format | Ratio (0.05 = 5%) | Ratio | **Percentage (5.2 = 5.2%)** |
| Video quartiles | % watched counts | **Rates 0.0–1.0** | Absolute counts |
| IDs type | String | **int64 → cast to STRING** | String |
| API access | REST (curl-able) | **Python SDK only** | REST (curl-able) |
| Conversions structure | `action_type` array | Segments per conversion action | **Flat metrics (no array)** |

---

## 📤 OUTPUT — Investigation Report

Return this JSON to the Coordinator after every investigation:

```json
{
  "platform": "Meta Marketing API",
  "auth": {
    "method": "OAuth 2.0",
    "required_credentials": ["app_id", "app_secret", "access_token"],
    "token_type": "System User Token",
    "expiry": "non-expiring"
  },
  "reporting_endpoint": "GET https://graph.facebook.com/v21.0/{act_id}/insights",
  "available_fields": [
    { "name": "impressions",   "type": "FLOAT64", "api_field": "impressions",              "note": "API returns STRING — cast to numeric" },
    { "name": "clicks",        "type": "FLOAT64", "api_field": "link_click_default_uas",   "note": "API returns STRING" },
    { "name": "spend",         "type": "FLOAT64", "api_field": "spend",                    "note": "API returns STRING — cast to float" },
    { "name": "ctr",           "type": "FLOAT64", "api_field": "DERIVED(clicks/impressions)", "note": "Not a direct field — derive or calculate" },
    { "name": "reach",         "type": "FLOAT64", "api_field": "reach",                    "note": "API returns STRING" },
    { "name": "conversions",   "type": "FLOAT64", "api_field": "conversions",              "note": "Generic total conversions" },
    { "name": "video_views",   "type": "FLOAT64", "api_field": "video_play_actions",       "note": "Use video_p100_watched for completions" },
    { "name": "campaign_name", "type": "STRING",  "api_field": "campaign_name",            "note": "" },
    { "name": "date",          "type": "TIMESTAMP","api_field": "date_start",              "note": "Format: YYYY-MM-DD" }
  ],
  "pagination": "cursor-based — iterate paging.after until paging.next is absent",
  "rate_limit": "no hard per-minute limit; async recommended for date ranges >7 days",
  "freshness_check": {
    "checked": true,
    "changes_detected": false,
    "delta": null
  }
}
```

This JSON is the handoff to the Data Modeler agent → `proponer_esquema_bq`.

---

## 📂 Reference Files

Load only the file relevant to the current platform:

- `references/meta.md` — full field tables (Structural + Performance + Conversions), pagination, all gotchas
- `references/google-ads.md` — GAQL fields, micros handling, video rates, conversion segments, gotchas
- `references/tiktok.md` — full field tables, flat conversion metrics, pagination, CTR normalization, gotchas