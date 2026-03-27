---
name: paid-media-api
description: API Investigator Agent (Data Sourcer). Specializes in researching external API documentation and extracting everything needed to build a read-only data pipeline: endpoints, authentication flows (OAuth, Bearer tokens, API keys), rate limits, pagination patterns, and raw JSON response schemas. Covers Meta Marketing API, Google Ads API, YouTube Data API, and TikTok Marketing API, but also handles unknown or custom APIs via search_web, read_documentation_url, and analyze_json_schema.   Always trigger this skill before writing any code or proposing any schema. This agent NEVER writes, creates, or modifies campaigns — read-only extraction only.

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
  │             → if changes detected: update reference file + flag delta to Coordinator
  │          3. Go to → EXTRACT FIELDS
  │
  └── NO  → 1. search_web("{api_name} official API documentation")
             2. read_documentation_url(top result)
                → extract: base_url, auth_method, reporting_endpoint,
                  available_fields, pagination, rate_limits
             3. analyze_json_schema(sample_response)
                → infer field names, types, nesting
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

| Platform | Docs URL | Auth pattern | Reference file |
|---|---|---|---|
| Meta Marketing API | https://developers.facebook.com/docs/marketing-apis/ | OAuth 2.0 → System User Token | `references/meta.md` |
| Google Ads API | https://developers.google.com/google-ads/api/docs/start | OAuth 2.0 + developer_token | `references/google-ads.md` |
| YouTube Data API v3 | https://developers.google.com/youtube/v3 | OAuth 2.0 / API Key | `references/google-ads.md` |
| TikTok Marketing API | https://business-api.tiktok.com/portal/docs | OAuth 2.0 → Access-Token header | `references/tiktok.md` |

For unknown APIs: run the full investigation flow, then save findings as a new file in `references/`.

---

## 🔐 AUTHENTICATION

### Meta (Facebook / Instagram)

```
1. App Review → get app_id + app_secret
2. OAuth flow → short-lived User Access Token (~1h)
3. Exchange for long-lived token (~60 days):
   GET https://graph.facebook.com/v21.0/oauth/access_token
     ?grant_type=fb_exchange_token
     &client_id={app_id}
     &client_secret={app_secret}
     &fb_exchange_token={short_lived_token}
4. Production: System User in Business Manager → non-expiring token
```

Permissions needed (read-only): `ads_read`, `read_insights`
Current API version: **v21.0** (always pin in URL)

---

### Google Ads API

```
Credentials needed:
  - client_id + client_secret  (Google Cloud Console)
  - developer_token            (Google Ads → Tools → API Center)
  - refresh_token              (OAuth consent flow)
  - login_customer_id          (MCC ID, no dashes)

Token refresh:
POST https://oauth2.googleapis.com/token
  grant_type=refresh_token &client_id={} &client_secret={} &refresh_token={}
```

Required headers on every request:
`Authorization: Bearer {token}` · `developer-token: {token}` · `login-customer-id: {mcc_id}`

---

### TikTok Marketing API

```
1. Register app → ads.tiktok.com/marketing_api/apps/
2. OAuth redirect → GET https://business-api.tiktok.com/portal/auth
3. Exchange code → POST /open_api/v1.3/oauth2/access_token/
   { "app_id": "...", "secret": "...", "auth_code": "..." }
   → returns access_token (long-lived) + advertiser_ids[]
```

All calls: `Header: Access-Token: {access_token}`

---

## 📡 REPORTING ENDPOINTS (read-only)

### Meta

```
GET https://graph.facebook.com/v21.0/{act_ACCOUNT_ID}/insights
  ?fields=campaign_name,impressions,clicks,spend,reach,ctr,
          actions,video_play_actions,video_p100_watched_actions
  &date_preset=last_7d
  &level=campaign          # campaign | adset | ad | account
  &access_token={token}

Pagination: cursor-based → loop on response.paging.next
Async (large ranges): POST /insights → poll report_run_id → GET /insights
```

---

### Google Ads

```
POST https://googleads.googleapis.com/v17/customers/{customer_id}/googleAds:search
{
  "query": "
    SELECT campaign.id, campaign.name,
      metrics.impressions, metrics.clicks, metrics.cost_micros,
      metrics.ctr, metrics.conversions, metrics.video_views,
      segments.date
    FROM campaign
    WHERE segments.date DURING LAST_7_DAYS
  "
}
cost_micros ÷ 1,000,000 = real currency value
Use search_stream for large result sets (avoids pagination overhead)
```

---

### TikTok

```
GET https://business-api.tiktok.com/open_api/v1.3/report/integrated/get/
  ?advertiser_id={id}
  &report_type=BASIC
  &dimensions=["campaign_id","stat_time_day"]
  &metrics=["spend","impressions","clicks","ctr","reach",
            "video_play_actions","video_watched_2s","video_views_p100"]
  &start_date=2024-01-01
  &end_date=2024-01-31    # max 30-day range per request
  Header: Access-Token: {token}

Pagination: page-based → increment page until page * page_size >= total_number
Always check: code == 0 before reading data
```

---

## ⚡ RATE LIMITS

| Platform | Limit | Notes |
|---|---|---|
| Meta | 200 calls/hour (app-level) | Check `X-Business-Use-Case-Usage` response header |
| Meta Insights | Async recommended for > 7 days | Use report_run_id flow |
| Google Ads | ~15,000 queries/day | Use `search_stream` for large results |
| TikTok | 10 req/sec · 60 req/min (reporting) | Max 30-day range per request |

---

## 🚨 COMMON ERRORS

| Platform | Error | Fix |
|---|---|---|
| Meta | `#190` Invalid token | Refresh or regenerate |
| Meta | `#17` Rate limit | Exponential backoff |
| Meta | `#100` Invalid parameter | Check field names in Graph API reference |
| Google Ads | `QUERY_ERROR` | Validate GAQL in Google Ads Query Builder |
| Google Ads | `AuthorizationError` | Check developer_token level (test vs production) |
| TikTok | `40001` Invalid token | Re-authenticate |
| TikTok | `50002` Rate limit | Wait and retry |
| TikTok | `40013` Invalid advertiser ID | Confirm advertiser_id matches token scope |

---

## 📤 OUTPUT — Investigation Report

Return this JSON structure to the Coordinator after every investigation:

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
    { "name": "impressions",   "type": "INTEGER", "api_field": "impressions" },
    { "name": "clicks",        "type": "INTEGER", "api_field": "clicks" },
    { "name": "spend",         "type": "FLOAT",   "api_field": "spend" },
    { "name": "ctr",           "type": "FLOAT",   "api_field": "ctr" },
    { "name": "conversions",   "type": "INTEGER", "api_field": "actions[offsite_conversion.fb_pixel_purchase]" },
    { "name": "video_views",   "type": "INTEGER", "api_field": "video_play_actions" },
    { "name": "campaign_name", "type": "STRING",  "api_field": "campaign_name" },
    { "name": "date",          "type": "DATE",    "api_field": "date_start" }
  ],
  "pagination": "cursor-based (paging.next)",
  "rate_limit": "200 calls/hour; async recommended for >7 days",
  "freshness_check": {
    "checked": true,
    "changes_detected": false,
    "delta": null
  }
}
```

This JSON is the handoff to the Data Modeler agent, which uses `available_fields` to propose a BigQuery DDL.

---

## 📂 Reference Files

- `references/meta.md` — Insights fields, breakdowns, pagination, batch requests
- `references/google-ads.md` — GAQL resources, metrics, segments, error handling
- `references/tiktok.md` — Reporting fields, pixel events, pagination, response structure

Load only the file relevant to the current platform.