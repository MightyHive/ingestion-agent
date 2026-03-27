# TikTok Marketing API — Deep Reference (Read-Only)

## MVP Read Query

```python
import requests

def get_tiktok_report(advertiser_id, access_token, start_date, end_date):
    url = "https://business-api.tiktok.com/open_api/v1.3/report/integrated/get/"
    headers = {"Access-Token": access_token}
    params = {
        "advertiser_id": advertiser_id,
        "report_type": "BASIC",
        "dimensions": '["campaign_id","stat_time_day"]',
        "metrics": '["spend","impressions","clicks","ctr","reach",'
                   '"video_play_actions","video_watched_2s","video_views_p100",'
                   '"result","cost_per_result"]',
        "start_date": start_date,   # "YYYY-MM-DD" — max 30-day range
        "end_date": end_date,
        "page_size": 100,
        "page": 1,
    }
    all_rows = []
    while True:
        r = requests.get(url, headers=headers, params=params).json()
        if r["code"] != 0:
            raise Exception(f"TikTok API error: {r['message']}")
        all_rows.extend(r["data"]["list"])
        page_info = r["data"]["page_info"]
        if params["page"] * params["page_size"] >= page_info["total_number"]:
            break
        params["page"] += 1
    return all_rows
```

> For date ranges > 30 days: call in 30-day chunks and concatenate results.

## Reporting Metrics Reference

```
# Spend & delivery
spend                   → total cost
impressions             → total impressions
reach                   → unique users reached
frequency               → impressions / reach

# Engagement
clicks                  → total clicks
ctr                     → click-through rate
cpc                     → cost per click

# Video
video_play_actions      → total video plays (started)
video_watched_2s        → 2-second views
video_watched_6s        → 6-second views
video_views_p25         → 25% completion
video_views_p50         → 50% completion
video_views_p75         → 75% completion
video_views_p100        → completed views (100%)
average_video_play      → avg watch duration (seconds)

# Conversions (pixel-based)
result                  → conversions (based on campaign objective)
cost_per_result         → cost per conversion
real_time_result        → real-time conversion count
```

## Dimensions

```
campaign_id, campaign_name
adgroup_id, adgroup_name
ad_id, ad_name
stat_time_day           → date (YYYY-MM-DD)
stat_time_hour          → hourly breakdown
age, gender             → demographic splits (report_type: AUDIENCE)
```

## Report Types

```
BASIC     → standard campaign/ad group/ad performance
AUDIENCE  → demographic splits (age, gender, location)
PLAYABLE  → playable ad metrics
CATALOG   → catalog/shopping ad metrics
```

## Pixel Events (conversion tracking)

```
ViewContent, Search, AddToWishlist, AddToCart,
InitiateCheckout, AddPaymentInfo, CompletePayment,
PlaceAnOrder, Download, Register, SubmitForm
```

## Response Structure

```json
{
  "code": 0,
  "message": "OK",
  "request_id": "...",
  "data": {
    "list": [
      {
        "dimensions": { "campaign_id": "123", "stat_time_day": "2024-01-01" },
        "metrics": { "impressions": "1000", "spend": "15.50", "ctr": "0.02" }
      }
    ],
    "page_info": { "page": 1, "page_size": 100, "total_number": 250, "total_page": 3 }
  }
}
```

⚠️ All metric values come back as **strings** — cast to float/int before storing.