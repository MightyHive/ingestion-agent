# Google Ads API - Field Reference

API Version: v17+ (library: `google-ads==29.2.0`)
Auth: Service Account via `google-ads.yaml` — requires `developer_token`, `login_customer_id`, `json_key_file_path`
Query language: **GAQL** (Google Ads Query Language — SQL-like)

> **Google Ads does NOT have a traditional REST API.** All data is fetched via the **Python SDK** using `ga_service.search_stream()`. The underlying REST endpoint is never called directly.

```python
from google.ads.googleads.client import GoogleAdsClient

client = GoogleAdsClient.load_from_storage("path/to/google-ads.yaml")
ga_service = client.get_service("GoogleAdsService")

stream = ga_service.search_stream(customer_id=customer_id, query=query)
for batch in stream:
    for row in batch.results:
        # access fields via row.campaign.id, row.metrics.clicks, etc.
```

---

## Hierarchy

```
MCC (Manager Account) -> Customer -> Campaign -> Ad Group -> Ad
```

---

## Domain: Structural

**GAQL resources:** `campaign`, `ad_group`, `ad_group_ad`
**Method:** `ga_service.search_stream(customer_id, query)`
**Frequency:** On-demand / weekly

### Campaign Fields

| Internal Name | GAQL Field | BQ Type | Notes |
|---|---|---|---|
| Channel_Campaign_ID | campaign.id | STRING | Cast to STRING — returned as int64 |
| Campaign | campaign.name | STRING | |
| Campaign_Status | campaign.status | STRING | Enum: ENABLED, PAUSED, REMOVED |
| Campaign_Objective | campaign.advertising_channel_type | STRING | Enum: SEARCH, DISPLAY, VIDEO, SHOPPING, PERFORMANCE_MAX |
| Campaign_Bidding | campaign.bidding_strategy_type | STRING | Enum: TARGET_CPA, TARGET_ROAS, MAXIMIZE_CONVERSIONS, etc. |
| Campaign_Budget | campaign_budget.amount_micros | FLOAT64 | Divide by 1,000,000 to get currency value |
| Currency | customer.currency_code | STRING | ISO 4217, e.g. "USD" |
| Account | customer.descriptive_name | STRING | |

### Ad Group Fields

| Internal Name | GAQL Field | BQ Type | Notes |
|---|---|---|---|
| Adset_ID | ad_group.id | STRING | Cast to STRING — returned as int64 |
| Adset | ad_group.name | STRING | |
| Adset_Status | ad_group.status | STRING | Enum: ENABLED, PAUSED, REMOVED |
| Adset_Type | ad_group.type | STRING | Enum: SEARCH_STANDARD, DISPLAY_STANDARD, VIDEO_TRUE_VIEW_IN_STREAM, etc. |

### Ad Fields

| Internal Name | GAQL Field | BQ Type | Notes |
|---|---|---|---|
| Ad_ID | ad_group_ad.ad.id | STRING | Cast to STRING — returned as int64 |
| Ad_Name | ad_group_ad.ad.name | STRING | |
| Ad_Status | ad_group_ad.status | STRING | Enum: ENABLED, PAUSED, REMOVED |
| Ad_Type | ad_group_ad.ad.type | STRING | Enum: RESPONSIVE_SEARCH_AD, EXPANDED_TEXT_AD, VIDEO_AD, etc. |
| Final_URLs | ad_group_ad.ad.final_urls | STRING | Repeated field — array of strings |
| Headlines | ad_group_ad.ad.responsive_search_ad.headlines | STRING | Repeated — array of {text, pinned_field} |
| Descriptions | ad_group_ad.ad.responsive_search_ad.descriptions | STRING | Repeated — array of {text, pinned_field} |

### Static Dimensions (injected at ingest, not from API)

| Field | Value |
|---|---|
| Channel | "Google" |
| Marketing_Channel | "Paid Search" or "Paid Video" depending on campaign type |
| Publisher_ID | `{{customer_id}}` |

---

## Domain: Performance

**GAQL resources:** `campaign`, `ad_group`, `ad_group_ad` with `metrics.*` and `segments.date`
**Method:** `ga_service.search_stream(customer_id, query)`
**Frequency:** Daily
**Lookback:** 7 days (rolling)
**Granularity:** `segments.date` (day)

### Example GAQL

```sql
SELECT
  campaign.id,
  ad_group_ad.ad.id,
  segments.date,
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.ctr,
  metrics.average_cpc,
  metrics.video_views,
  metrics.video_quartile_p25_rate,
  metrics.video_quartile_p50_rate,
  metrics.video_quartile_p75_rate,
  metrics.video_quartile_p100_rate
FROM ad_group_ad
WHERE segments.date DURING LAST_7_DAYS
```

### Fields

| Internal Name | GAQL Field | BQ Type | Notes |
|---|---|---|---|
| Record_Date | segments.date | TIMESTAMP | Format: `YYYY-MM-DD` |
| Channel_Campaign_ID | campaign.id | STRING | |
| Ad_ID | ad_group_ad.ad.id | STRING | |
| Impressions | metrics.impressions | FLOAT64 | Returned as int64 |
| Clicks | metrics.clicks | FLOAT64 | Returned as int64 |
| Cost | metrics.cost_micros | FLOAT64 | Divide by 1,000,000 — always stored in micros |
| CTR | metrics.ctr | FLOAT64 | Already a ratio (0.05 = 5%) |
| Avg_CPC | metrics.average_cpc | FLOAT64 | Also in micros — divide by 1,000,000 |
| VideoViews | metrics.video_views | FLOAT64 | |
| VideoViews_25% | metrics.video_quartile_p25_rate | FLOAT64 | Rate (0.0-1.0), not count |
| VideoViews_50% | metrics.video_quartile_p50_rate | FLOAT64 | Rate |
| VideoViews_75% | metrics.video_quartile_p75_rate | FLOAT64 | Rate |
| VideoViews_100% | metrics.video_quartile_p100_rate | FLOAT64 | Rate |

> `cost_micros` and `average_cpc` are always in micros. Divide by 1,000,000 before storing.
> Video quartile fields are rates (0.0-1.0), not absolute view counts.

---

## Domain: Conversions

**GAQL resources:** `campaign` or `ad_group_ad` with `metrics.conversions`, `metrics.all_conversions`, `segments.conversion_action`
**Method:** `ga_service.search_stream(customer_id, query)`
**Frequency:** Daily
**Lookback:** 7 days (rolling)

### Attribution Model

Google Ads reports conversions per conversion action and attribution model. We capture:

| Metric | Meaning |
|---|---|
| `metrics.conversions` | Primary conversions (click-through, using account attribution model) |
| `metrics.all_conversions` | All conversions including view-through and cross-device |
| `metrics.view_through_conversions` | View-through conversions only |
| `metrics.conversions_value` | Revenue attributed to conversions |

### Key Conversion Fields

| Internal Name | GAQL Field | BQ Type | Notes |
|---|---|---|---|
| Conv_click | metrics.conversions | FLOAT64 | Click-attributed, primary actions only |
| Conv_all | metrics.all_conversions | FLOAT64 | Includes view-through and secondary actions |
| Conv_view | metrics.view_through_conversions | FLOAT64 | View-through only |
| Conv_value | metrics.conversions_value | FLOAT64 | Revenue from conversions |
| Conv_action | segments.conversion_action_name | STRING | Name of the specific conversion action |
| Conv_action_category | segments.conversion_action_category | STRING | Enum: PURCHASE, LEAD, SIGNUP, PAGE_VIEW, etc. |

### Splitting by Conversion Action

To get per-action breakdown, add `segments.conversion_action_name` to the GAQL query:

```sql
SELECT
  campaign.id,
  segments.date,
  segments.conversion_action_name,
  segments.conversion_action_category,
  metrics.conversions,
  metrics.all_conversions,
  metrics.view_through_conversions,
  metrics.conversions_value
FROM campaign
WHERE segments.date DURING LAST_7_DAYS
```

---

## Pagination

`search_stream` handles pagination automatically — no manual cursor management needed. Results stream in batches of ~10,000 rows.

If using `search` instead (not recommended):
- `nextPageToken` is returned in the response and passed in the next request
- Default page size: 10,000 rows

**Always prefer `search_stream` over `search`** for ingestion.

---

## Rate Limits

| Resource | Limit |
|---|---|
| Daily operations | ~15,000 (scales with account spend) |
| Rows per stream batch | ~10,000 |
| Mutate operations per request | 2,000 |

> If rate limit hit: reduce query frequency or split by date range. Do not re-call — read from GCS buffer.

---

## Common Gotchas

| Issue | Detail |
|---|---|
| No REST calls | All access via Python SDK — not curl-able like Meta or TikTok |
| `cost_micros` | Always divide by 1,000,000 — never store raw micros in BQ |
| IDs are int64 | Campaign/ad group/ad IDs returned as integers — cast to STRING |
| Video quartiles are rates | `video_quartile_p25_rate` is 0.0-1.0, not a count |
| `conversions` vs `all_conversions` | `conversions` = primary actions only; `all_conversions` = everything |
| Repeated headlines/descriptions | RSA headlines and descriptions are arrays of objects, not flat strings |
| `segments.date` required for daily | Without it, metrics aggregate across the full date range |
| Performance Max campaigns | Limited field visibility — many ad-level fields unavailable for PMax |