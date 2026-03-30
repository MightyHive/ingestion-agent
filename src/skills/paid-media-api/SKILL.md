---
name: paid-media-api
description: "API Investigator Agent (Data Sourcer). Specializes in researching external API documentation and extracting everything needed to build a read-only data pipeline: endpoints, authentication flows (OAuth, Bearer tokens, API keys), rate limits, pagination patterns, and raw JSON response schemas. Covers Meta Marketing API, Google Ads API, YouTube Data API, and TikTok Marketing API, but also handles unknown or custom APIs via search_web, read_documentation_url, and analyze_json_schema. Always trigger this skill before writing any code or proposing any schema. This agent NEVER writes, creates, or modifies campaigns — read-only extraction only."
---

# Paid Media API Skill — Read-Only Data Extraction

Extracts a **complete field catalog** for the platform plus the minimum infrastructure
metadata (auth, endpoint, pagination, rate limits) needed by the Data Architect and
Software Engineer downstream.

Scope: **authentication**, **reporting endpoint**, **all available fields with categories,
canonical matches, notes, and semantics**, **pagination**, **rate limits**.
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
                  all available fields, pagination, rate_limits
             3. analyze_json_schema(sample_response) if JSON available
             4. Go to → EXTRACT FIELDS

EXTRACT FIELDS (see rules below)
  → Go to → OUTPUT
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

### Meta
```
Primary endpoint: GET /{account_id}/insights
Level:    campaign + ad
Lookback: 7 days rolling
Granularity: date_start (day)
⚠️ ALL numeric fields arrive as STRINGS — always cast before loading to BQ.
⚠️ CTR is not a direct field — derive as DERIVED(clicks/impressions).
⚠️ Conversions come from the same endpoint via the action_type array.
```

### Google Ads
```
Primary endpoint: ga_service.search_stream(customer_id, query)
Resource: ad_group_ad with metrics.* and segments.date
Lookback: 7 days rolling
Granularity: segments.date (required for daily rows — omitting it aggregates everything)
⚠️ cost_micros: always divide by 1,000,000 — never store raw micros.
⚠️ video_quartile_p*_rate: RATES (0.0–1.0), not counts.
⚠️ IDs (campaign, ad group, ad) are int64 — cast to STRING.
⚠️ metrics.conversions = primary actions only.
⚠️ metrics.all_conversions = everything including view-through and secondary actions.
```

### TikTok
```
Primary endpoint: GET /report/integrated/get/  (report_type: BASIC)
Lookback: 7 days rolling
Granularity: stat_time_day
⚠️ spend is already in currency units (NOT micros) — do NOT divide.
⚠️ ctr is a PERCENTAGE (5.2 = 5.2%), not a ratio — normalize for cross-platform.
⚠️ video_views_p* are ABSOLUTE COUNTS (opposite of Google Ads rates).
⚠️ stat_time_day includes time component (YYYY-MM-DD HH:MM:SS) — truncate to date.
⚠️ Max date range per request: 30 days — chunk for historical backfills.
⚠️ Conversions are FLAT METRICS per type — NOT an action_type array like Meta.
```

---

## 🗂️ EXTRACT FIELDS — Rules

### Step 1 — Read ALL fields from the reference file
Extract every field across ALL domains: structural + performance + conversions.
Do not stop at 9. Typical output: 25-50 entries.

### Step 2 — Map the 9 canonical metrics
Always attempt to map these, in this order:

| # | Canonical key  | Meta                              | Google Ads                     | TikTok              |
|---|----------------|-----------------------------------|--------------------------------|---------------------|
| 1 | impressions    | impressions                       | metrics.impressions            | impressions         |
| 2 | clicks         | link_click_default_uas            | metrics.clicks                 | clicks              |
| 3 | spend          | spend                             | metrics.cost_micros ÷ 1e6      | spend               |
| 4 | ctr            | DERIVED(clicks/impressions)       | metrics.ctr                    | ctr                 |
| 5 | conversions    | conversions                       | metrics.conversions            | conversion          |
| 6 | video_views    | video_p100_watched_default_uas    | metrics.video_views            | video_play_actions  |
| 7 | reach          | reach                             | metrics.impressions_reach      | reach               |
| 8 | campaign_name  | campaign_name                     | campaign.name                  | campaign_name       |
| 9 | date           | date_start                        | segments.date                  | stat_time_day       |

If a platform does not expose a canonical metric, include it with api_field="NOT_AVAILABLE".
Only ONE field per platform may claim each canonical key.

### Step 3 — Add all remaining fields
Include at minimum (when available):
- Structural: campaign_id, adset_id, ad_id, campaign_status, campaign_objective, ad_type, currency
- Extended performance: cpc, cpm, frequency, avg_cpc
- Video quartiles: p25, p50, p75, p100 (note whether rates or counts)
- Conversion breakdowns: purchase, lead, add_to_cart, app_install, all_conversions,
  view-through, conversion_value, per-attribution-window variants
- Cost sub-types: budget, bid_price

### Step 4 — Populate per-field metadata

| Attribute        | Rule |
|------------------|------|
| `api_field`      | Exact name from API/docs. Dot notation for nested. DERIVED(formula) if calculated. |
| `label`          | Verbatim from docs or JSON — do NOT normalize spelling. |
| `type`           | FLOAT64 \| INTEGER \| STRING \| TIMESTAMP \| DATE \| BOOLEAN |
| `category`       | structural \| performance \| conversion \| other |
| `canonical_match`| One of the 9 keys, or null. One field per platform per canonical key. |
| `note`           | Required for any cast, division, format, or normalization quirk. |
| `semantics`      | Required for canonical_match="conversions". Also required for CTR, spend, all_conversions, and any metric that counts differently across platforms. |

### Step 5 — Order the list
1. The 9 canonical fields first (in canonical order), even if api_field="NOT_AVAILABLE".
2. Remaining fields: structural → performance → conversion → other, then alpha by label.

### Step 6 — Set discovery metadata
```
total_fields_discovered = len(available_fields)
canonical_fields_found  = count of entries with canonical_match != null
discovery_method        = "docs_only" | "json_schema" | "docs_and_schema"
```

---

## ⚡ RATE LIMITS

| Platform    | Limit                           | Pagination                                           |
|-------------|---------------------------------|------------------------------------------------------|
| Meta        | No hard per-minute limit        | Cursor-based — iterate paging.cursors.after          |
| Google Ads  | ~15,000 queries/day             | search_stream handles automatically                  |
| TikTok      | 10 req/sec · 60 req/min         | Page-based — increment page until page >= total_page |

---

## 🚨 CROSS-PLATFORM GOTCHAS

| Issue               | Meta                          | Google Ads                  | TikTok                        |
|---------------------|-------------------------------|-----------------------------|-------------------------------|
| Numeric as strings  | ✅ Yes — cast everything      | ❌ Native types             | ❌ Mostly native              |
| Spend unit          | Float (currency)              | **Micros ÷ 1,000,000**      | Float (currency, NOT micros)  |
| CTR format          | **Derived** (no direct field) | Ratio (0.05 = 5%)           | **Percentage (5.2 = 5.2%)**   |
| Video quartiles     | Counts                        | **Rates 0.0–1.0**           | Counts                        |
| IDs type            | String                        | **int64 → cast to STRING**  | String                        |
| API access          | REST                          | **Python SDK only**         | REST                          |
| Conversions shape   | action_type array             | Segments per action         | **Flat metrics per type**     |

---

## 📤 OUTPUT FORMAT

The full `APIResearcherLOL` JSON. Key points:
- `available_fields` is the complete catalog — not limited to 9 entries.
- `semantics` must be populated for every conversion field and for CTR/spend where behavior differs across platforms.
- `total_fields_discovered`, `canonical_fields_found`, `discovery_method` must always be set.
- `summary` must state: platform, action, total fields, canonical coverage (X/9), key gotchas, freshness result.

Abbreviated example (Meta, canonical fields only for brevity):

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
    {
      "api_field": "impressions",
      "label": "impressions",
      "type": "FLOAT64",
      "category": "performance",
      "canonical_match": "impressions",
      "note": "API returns STRING — cast to FLOAT64",
      "semantics": null
    },
    {
      "api_field": "link_click_default_uas",
      "label": "link_click_default_uas",
      "type": "FLOAT64",
      "category": "performance",
      "canonical_match": "clicks",
      "note": "API returns STRING — cast to FLOAT64",
      "semantics": null
    },
    {
      "api_field": "spend",
      "label": "spend",
      "type": "FLOAT64",
      "category": "performance",
      "canonical_match": "spend",
      "note": "API returns STRING — cast to FLOAT64",
      "semantics": "Total spend in account currency. Includes all fees."
    },
    {
      "api_field": "DERIVED(link_click_default_uas / impressions)",
      "label": "ctr",
      "type": "FLOAT64",
      "category": "performance",
      "canonical_match": "ctr",
      "note": "Not a direct field — calculate as clicks / impressions. Result is a ratio (0.05 = 5%).",
      "semantics": "Meta does not expose CTR directly — must be derived. Result is a ratio, unlike TikTok which returns a percentage."
    },
    {
      "api_field": "conversions",
      "label": "conversions",
      "type": "FLOAT64",
      "category": "conversion",
      "canonical_match": "conversions",
      "note": "API returns STRING — cast to FLOAT64",
      "semantics": "Total conversions across all action types and attribution windows combined. For per-type or per-window breakdown, use the action_type array fields."
    },
    {
      "api_field": "video_p100_watched_default_uas",
      "label": "video_p100_watched_default_uas",
      "type": "FLOAT64",
      "category": "performance",
      "canonical_match": "video_views",
      "note": null,
      "semantics": "100% video completions. Use video_play_actions for total plays including partial views."
    },
    {
      "api_field": "reach",
      "label": "reach",
      "type": "FLOAT64",
      "category": "performance",
      "canonical_match": "reach",
      "note": "API returns STRING — cast to FLOAT64",
      "semantics": null
    },
    {
      "api_field": "campaign_name",
      "label": "campaign_name",
      "type": "STRING",
      "category": "structural",
      "canonical_match": "campaign_name",
      "note": null,
      "semantics": null
    },
    {
      "api_field": "date_start",
      "label": "date_start",
      "type": "TIMESTAMP",
      "category": "other",
      "canonical_match": "date",
      "note": "Format: YYYY-MM-DD",
      "semantics": null
    }
    // ... all remaining non-canonical fields follow, grouped by category
  ],
  "total_fields_discovered": 34,
  "canonical_fields_found": 9,
  "discovery_method": "docs_only",
  "pagination": "cursor-based — iterate paging.cursors.after until paging.next is absent",
  "rate_limit": "no hard per-minute limit; async recommended for date ranges > 7 days",
  "freshness_check": {
    "checked": true,
    "changes_detected": false,
    "delta": null
  },
  "missing_inputs": [],
  "summary": "Meta Marketing API investigated via freshness check. 34 fields catalogued (9/9 canonical metrics mapped). All numeric fields arrive as strings and must be cast before BQ load; CTR must be derived as there is no direct field. The conversions field is an aggregate across all action types and windows — per-type breakdown requires separate action_type array fields. No changes detected in live documentation."
}
```

---

## 📂 Reference Files

- `references/meta.md` — full field tables (Structural + Performance + Conversions), pagination, all gotchas
- `references/google-ads.md` — GAQL fields, micros handling, video rates, conversion segments, gotchas
- `references/tiktok.md` — full field tables, flat conversion metrics, pagination, CTR normalization, gotchas
