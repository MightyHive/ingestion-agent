# META MARKETING API

Base URL: https://graph.facebook.com/v21.0/
API Version: v21.0
Auth: OAuth2

---

## Hierarchy
```
Ad Account → Campaign → Ad Set → Ad → Creative
```
---

## Domain: Structural

**Endpoint:** `GET /{account_id}/campaigns`, `/{campaign_id}/adsets`, `/{adset_id}/ads`
**Frequency:** On-demand / weekly
**Lookback:** 180 days

### Fields

| Internal Name | API Field (`temp_name`) | BQ Type | Notes |
|---|---|---|---|
| Channel_Campaign_ID | campaign_id | STRING | ⚠️ Always STRING, even though it looks like an int |
| Campaign | campaign_name | STRING | |
| Campaign_Status | campaign_status | STRING | Enum: ACTIVE, PAUSED, DELETED, ARCHIVED |
| Campaign_Objective | campaign_objective | STRING | Enum: CONVERSIONS, REACH, BRAND_AWARENESS, etc. |
| Adset_ID | adset_id | STRING | ⚠️ Always STRING |
| Adset | adset_name | STRING | |
| Adset_Status | adset_status | STRING | |
| Ad_ID | ad_id | STRING | ⚠️ Always STRING |
| Ad_Name | ad_name | STRING | |
| Ad_Status | ad_status | STRING | |
| Creative_ID | creative_id | STRING | |
| Creative_Name | creative_name | STRING | |
| Creative_Status | creative_status | STRING | |
| Ad_Type | object_type | STRING | Enum: VIDEO, IMAGE, CAROUSEL, etc. |
| Currency | currency | STRING | ISO 4217, e.g. "USD" |
| Account | account_name | STRING | |
| Ad_Preview_Link | ad_preview_link | STRING | ⚠️ Expires — do not cache long-term |
| Ad_Create_Date | ad_create_date | TIMESTAMP | ⚠️ Format: `%Y-%m-%dT%H:%M:%E*S%Ez` — requires custom parsing |
 
### Repeated Fields (ARRAY)
 
These fields come as arrays because a single ad can reference multiple creatives:
 
| Internal Name | API Field | Notes |
|---|---|---|
| Caption | caption | Array of strings |
| Description | description | Array of strings |
| Link | link | Array of destination URLs |
| Name | name | Array of creative names |
| Video_ID | video_id | Array of video IDs |
| Title | title | Array of headline strings |
| Ad_Text | message | Array of body copy strings |
| Image_URL | image_url | Array of image URLs |
 
### Static Dimensions (injected at ingest, not from API)
 
| Field | Value |
|---|---|
| Channel | "Facebook" |
| Marketing_Channel | "Paid Social" |
| Publisher_ID | `{{account_id}}` |

---

## Domain: Perfomance

**Endpoint:** `GET /{account_id}/insights`
**Frequency:** Daily
**Lookback:** 7 days (rolling)
**Granularity:** `date_start` (day)
**Level:** campaign + ad

### Fields

| Internal Name | API Field (`temp_name`) | BQ Type | Notes |
|---|---|---|---|
| Record_Date | date_start | TIMESTAMP | Format: `%Y-%m-%d` |
| Channel_Campaign_ID | campaign_id | STRING | |
| Ad_ID | ad_id | STRING | |
| Impressions | impressions | FLOAT64 | ⚠️ API returns STRING — cast to numeric |
| Clicks | link_click_default_uas | FLOAT64 | ⚠️ API returns STRING |
| Cost | spend | FLOAT64 | ⚠️ API returns STRING — cast to float |
| Reach | reach | FLOAT64 | ⚠️ API returns STRING |
| Conv | conversions | FLOAT64 | Generic total conversions |
| VideoViews_25% | video_p25_watched_default_uas | FLOAT64 | |
| VideoViews_50% | video_p50_watched_default_uas | FLOAT64 | |
| VideoViews_75% | video_p75_watched_default_uas | FLOAT64 | |
| VideoViews_100% | video_p100_watched_default_uas | FLOAT64 | |
| VideoViews_30sec | video_30_sec_watched_default_uas | FLOAT64 | |
 
> ⚠️ **All numeric fields arrive as strings from the API.** Always cast before loading to BigQuery.

---

## Domain: Conversions

**Endpoint:** `GET /{account_id}/insights` 
**Frequency:** Daily
**Lookback:** 7 days (rolling)
**Granularity:** `date_start` (day)
**Level:** campaign + ad

Meta reports conversions per **attribution window**. We capture two windows:
 
| Suffix | Meaning |
|---|---|
| `_1d_click` | 1-day click attribution |
| `_7d_click` | 7-day click attribution |
| `_28d_click` | 28-day click attribution |
| `_1d_view` | 1-day view-through attribution |
| `_7d_view` | 7-day view-through attribution |
| `_28d_view` | 28-day view-through attribution |

### Key Conversion Types
 
| Action Type (API) | Description |
|---|---|
| `offsite_conversion.fb_pixel_purchase` | Website purchase (Pixel) |
| `offsite_conversion.fb_pixel_lead` | Website lead (Pixel) |
| `offsite_conversion.fb_pixel_complete_registration` | Registration |
| `offsite_conversion.fb_pixel_add_to_cart` | Add to cart |
| `offsite_conversion.fb_pixel_initiate_checkout` | Checkout started |
| `app_custom_event.fb_mobile_purchase` | In-app purchase |
| `app_install` | App install |
| `lead` | Lead (native/Lead Ads) |
| `link_click` | Link click |
| `landing_page_view` | Landing page view |
 
---

## Pagination

Meta uses **cursor-based pagination**:
 
```json
{
  "paging": {
    "cursors": {
      "before": "...",
      "after": "..."
    },
    "next": "https://graph.facebook.com/..."
  }
}
```
Iterate using `after` cursor until `next` is absent.
