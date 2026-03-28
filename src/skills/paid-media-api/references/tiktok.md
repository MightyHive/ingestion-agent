# TIK TOK API FOR BUSINESS

Base URL: https://business-api.tiktok.com/open_api/v1.3/
API Version: v1.3
Auth: OAuth2

---

## Hierarchy
```
Advertiser (advertiser_id) → Campaign (campaign_id) → Ad Group (adgroup_id) → Ad (ad_id)
```
---

## Domain: Structural

**Endpoints:** `GET /campaign/get/`, `GET /adgroup/get/`, `GET /ad/get/`
> ⚠️ Unlike Meta (where `account_id` goes in the URL path), TikTok passes `advertiser_id` as a **query parameter**: `GET /campaign/get/?advertiser_id=123`. The path itself is always static.
**Frequency:** On-demand / weekly
**Lookback:** 180 days
 
### Campaign Fields

Source: `GET /campaign/get/`
 
| Internal Name | API Field | BQ Type | Notes |
|---|---|---|---|
| Publisher_ID | advertiser_id | STRING | Present at every level of the hierarchy |
| Channel_Campaign_ID | campaign_id | STRING | ⚠️ Always STRING — looks like int |
| Campaign | campaign_name | STRING | |
| Campaign_Objective | objective | STRING | Broad category, e.g. `LANDING_PAGE` |
| Campaign_Objective_Type | objective_type | STRING | Enum: TRAFFIC, CONVERSIONS, APP_INSTALL, VIDEO_VIEWS, REACH, LEAD_GENERATION |
| Campaign_Type | campaign_type | STRING | Enum: REGULAR_CAMPAIGN |
| Campaign_Status | operation_status | STRING | User-set status. Enum: ENABLE, DISABLE, DELETE |
| Campaign_Delivery_Status | secondary_status | STRING | Actual delivery state, e.g. `CAMPAIGN_STATUS_ENABLE` |
| Campaign_Budget | budget | FLOAT64 | In account currency |
| Budget_Mode | budget_mode | STRING | Enum: BUDGET_MODE_DAY, BUDGET_MODE_TOTAL |
| Campaign_Create_Time | create_time | TIMESTAMP | |
| Campaign_Modify_Time | modify_time | TIMESTAMP | |
 
 
### Ad Group Fields

Source: `GET /adgroup/get/`
 
| Internal Name | API Field | BQ Type | Notes |
|---|---|---|---|
| Publisher_ID | advertiser_id | STRING | Repeated at every level |
| Channel_Campaign_ID | campaign_id | STRING | |
| Campaign | campaign_name | STRING | |
| Adset_ID | adgroup_id | STRING | ⚠️ Always STRING |
| Adset | adgroup_name | STRING | |
| Adset_Status | operation_status | STRING | Enum: ENABLE, DISABLE, DELETE |
| Adset_Delivery_Status | secondary_status | STRING | Actual delivery state, e.g. `ADGROUP_STATUS_CREATE` |
| Placement_Type | placement_type | STRING | Enum: PLACEMENT_TYPE_NORMAL, PLACEMENT_TYPE_AUTOMATIC |
| Placements | placements | STRING | ⚠️ Repeated — array, e.g. `["PLACEMENT_TIKTOK"]` |
| Optimization_Goal | optimization_goal | STRING | Enum: CLICK, CONVERT, REACH, VIDEO_VIEW, etc. |
| Bid_Type | bid_type | STRING | Enum: BID_TYPE_NO_BID, BID_TYPE_CUSTOM, etc. |
| Bid_Price | bid_price | FLOAT64 | In account currency |
| Billing_Event | billing_event | STRING | Enum: CPC, CPM, etc. |
| Pacing | pacing | STRING | Enum: PACING_MODE_SMOOTH, PACING_MODE_FAST |
| Schedule_Type | schedule_type | STRING | Enum: SCHEDULE_START_END, SCHEDULE_FROM_NOW |
| Schedule_Start | schedule_start_time | TIMESTAMP | |
| Schedule_End | schedule_end_time | TIMESTAMP | |
| Adset_Budget | budget | FLOAT64 | In account currency |
| Budget_Mode | budget_mode | STRING | |
| Adset_Create_Time | create_time | TIMESTAMP | |
| Adset_Modify_Time | modify_time | TIMESTAMP | |
 
### Ad Fields

Source: `GET /ad/get/`
 
| Internal Name | API Field | BQ Type | Notes |
|---|---|---|---|
| Publisher_ID | advertiser_id | STRING | Repeated at every level |
| Channel_Campaign_ID | campaign_id | STRING | |
| Campaign | campaign_name | STRING | |
| Adset_ID | adgroup_id | STRING | |
| Adset | adgroup_name | STRING | |
| Ad_ID | ad_id_v2 | STRING | ⚠️ Field is `ad_id_v2`, NOT `ad_id` |
| Ad_Name | ad_name | STRING | |
 
### Static Dimensions (injected at ingest, not from API)
 
| Field | Value |
|---|---|
| Channel | "TikTok" |
| Marketing_Channel | "Paid Social" |
| Publisher_ID | `{{advertiser_id}}` |
 
 ---

## Domain: Perfomance

 
**Endpoint:** `GET /report/integrated/get/`
**Frequency:** Daily
**Lookback:** 7 days (rolling)
**Granularity:** `stat_time_day`
**`report_type`:** `BASIC`
 
### Request Parameters
 
```json
{
  "advertiser_id": "...",
  "report_type": "BASIC",
  "dimensions": ["campaign_id", "adgroup_id", "ad_id", "stat_time_day"],
  "metrics": ["spend", "impressions", "clicks", "reach", "ctr", "cpc", "cpm",
              "video_play_actions", "video_watched_2s", "video_watched_6s",
              "video_views_p25", "video_views_p50", "video_views_p75", "video_views_p100"],
  "start_date": "2024-01-01",
  "end_date": "2024-01-07",
  "page_size": 1000
}
```
 
### Fields
 
| Internal Name | API Field | BQ Type | Notes |
|---|---|---|---|
| Record_Date | stat_time_day | TIMESTAMP | Format: `YYYY-MM-DD HH:MM:SS` — truncate to date |
| Channel_Campaign_ID | campaign_id | STRING | |
| Adset_ID | adgroup_id | STRING | |
| Ad_ID | ad_id | STRING | |
| Impressions | impressions | FLOAT64 | |
| Clicks | clicks | FLOAT64 | |
| Cost | spend | FLOAT64 | In account currency — already decimal (not micros) |
| Reach | reach | FLOAT64 | |
| CTR | ctr | FLOAT64 | ⚠️ Percentage format (5.2 = 5.2%), not ratio |
| CPM | cpm | FLOAT64 | |
| CPC | cpc | FLOAT64 | |
| VideoPlays | video_play_actions | FLOAT64 | Total video plays |
| VideoViews_2s | video_watched_2s | FLOAT64 | |
| VideoViews_6s | video_watched_6s | FLOAT64 | |
| VideoViews_25% | video_views_p25 | FLOAT64 | Absolute count (not rate) |
| VideoViews_50% | video_views_p50 | FLOAT64 | Absolute count |
| VideoViews_75% | video_views_p75 | FLOAT64 | Absolute count |
| VideoViews_100% | video_views_p100 | FLOAT64 | Absolute count |
 
> ⚠️ TikTok `spend` is already in currency units (not micros). Do NOT divide.
> ⚠️ `ctr` is a percentage (e.g. `5.2`), not a ratio (not `0.052`). Normalize if comparing with other platforms.
> ⚠️ Video quartile fields are **absolute counts**, unlike Google Ads which returns rates.
 
---
 
## Domain: Conversions
 
**Endpoint:** `GET /report/integrated/get/`
**`report_type`:** `BASIC`
**Frequency:** Daily
 
### Attribution Windows
 
TikTok reports conversions using these attribution windows:
 
| Window | Description |
|---|---|
| `click_7d` | 7-day click-through (default) |
| `click_1d` | 1-day click-through |
| `click_28d` | 28-day click-through |
| `view_1d` | 1-day view-through |
| `view_7d` | 7-day view-through |
| `view_28d` | 28-day view-through |
 

 
### Key Conversion Metrics
 
| Internal Name | API Field | BQ Type | Notes |
|---|---|---|---|
| Conv_total | conversion | FLOAT64 | Total conversions (default attribution) |
| Conv_value | total_purchase_value | FLOAT64 | Revenue from purchase conversions |
| Conv_purchase | purchase | FLOAT64 | Purchase events |
| Conv_add_to_cart | add_to_cart | FLOAT64 | |
| Conv_initiate_checkout | initiate_checkout | FLOAT64 | |
| Conv_complete_payment | complete_payment | FLOAT64 | |
| Conv_lead | on_web_order | FLOAT64 | Lead/form submission |
| Conv_app_install | app_install | FLOAT64 | App installs |
| Conv_registration | registration | FLOAT64 | Account registrations |
| Conv_view_content | view_content | FLOAT64 | Content views |
| Conv_click_button | click_button | FLOAT64 | CTA button clicks |
| Conv_view | value_per_1000_reached | FLOAT64 | View-through metric |
 
> ⚠️ TikTok does **not** use an `action_type` array like Meta. Each conversion type is a **separate flat metric** in the API response.

---

## Pagination

TikTok uses **page-based pagination**:

```json
{
  "data": {
    "page_info": {
      "page": 1,
      "page_size": 1000,
      "total_number": 5000,
      "total_page": 5
    },
    "list": [...]
  }
}
```
 
Iterate by incrementing `page` param until `page >= total_page`. Max `page_size` is 1,000.
 
> ⚠️ Max date range per single request: **30 days**. For longer periods, split into multiple 30-day requests.
 
---
 
## Rate Limits
 
| Resource | Limit |
|---|---|
| General API | 10 req/sec per advertiser |
| Reporting API | 60 req/min |
| Max date range per request | 30 days |
| Max page size | 1,000 rows |
 
> If rate limit hit: wait and retry with exponential backoff. Read from GCS buffer instead of re-calling.
 
---
 
## Common Gotchas
 
| Issue | Detail |
|---|---|
| `spend` is not micros | Already in currency units — do NOT divide by 1,000,000 |
| `ctr` is a percentage | `5.2` means 5.2%, not 0.052 — normalize before cross-platform comparisons |
| No `action_type` array | Conversions are flat metrics, not an array like Meta — different ingestion logic |
| Video quartiles are counts | `video_views_p25` is an absolute number, not a rate (opposite of Google Ads) |
| `stat_time_day` format | Includes time component `YYYY-MM-DD HH:MM:SS` — truncate to date |
| IDs are strings | All IDs (`campaign_id`, `adgroup_id`, `ad_id`) already come as strings |
| 30-day report limit | Must chunk requests by date range for historical backfills |
| `primary_status` vs `operation_status` | `primary_status` reflects actual delivery status; `operation_status` reflects user-set status |