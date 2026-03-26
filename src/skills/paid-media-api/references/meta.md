# Meta Marketing API — Deep Reference (Read-Only)

## MVP Read Query

```python
import requests

def get_insights(account_id, access_token, fields, date_preset="last_30d", level="campaign"):
    url = f"https://graph.facebook.com/v21.0/act_{account_id}/insights"
    params = {
        "fields": ",".join(fields),
        "date_preset": date_preset,
        "level": level,
        "limit": 100,
        "access_token": access_token,
    }
    results = []
    while url:
        r = requests.get(url, params=params).json()
        results.extend(r.get("data", []))
        url = r.get("paging", {}).get("next")
        params = {}  # next URL already includes params
    return results

# Usage:
fields = ["campaign_name", "impressions", "clicks", "spend", "ctr",
          "reach", "cpm", "cpc", "actions", "video_play_actions"]
data = get_insights("YOUR_ACCOUNT_ID", "YOUR_TOKEN", fields)
```

## Insights Fields Reference

```
# Core performance
impressions, reach, frequency, clicks, unique_clicks,
spend, cpm, cpc, ctr, cpp

# Actions (filter by action_type)
actions                          → list of {action_type, value}
action_values                    → revenue values per action
cost_per_action_type

# Key action_types for conversions:
offsite_conversion.fb_pixel_purchase
offsite_conversion.fb_pixel_add_to_cart
lead
link_click
app_install
omni_purchase

# Video
video_play_actions               → views (any duration)
video_p25_watched_actions        → 25% watched
video_p50_watched_actions        → 50% watched
video_p75_watched_actions        → 75% watched
video_p100_watched_actions       → completed views
video_avg_time_watched_actions   → avg watch time in ms
```

## Date Presets

```
today, yesterday, last_7d, last_14d, last_30d,
last_month, this_month, last_quarter, this_year
```

Or use explicit range: `&time_range={"since":"2024-01-01","until":"2024-01-31"}`

## Granularity (level parameter)

```
account   → one row per account
campaign  → one row per campaign
adset     → one row per ad set
ad        → one row per ad
```

## Breakdowns (optional splits)

```
age, gender, country, region,
publisher_platform, platform_position, device_platform
```

Add to request: `&breakdowns=age,gender`

## Async Insights (for large date ranges or many accounts)

```python
# Step 1: create job
r = requests.post(
    f"https://graph.facebook.com/v21.0/act_{ACCOUNT_ID}/insights",
    params={"access_token": TOKEN},
    data={"fields": "impressions,spend,clicks", "date_preset": "last_90d", "level": "campaign"}
).json()
report_run_id = r["report_run_id"]

# Step 2: poll until complete
import time
while True:
    status = requests.get(
        f"https://graph.facebook.com/v21.0/{report_run_id}",
        params={"fields": "async_status,async_percent_completion", "access_token": TOKEN}
    ).json()
    if status["async_status"] == "Job Completed":
        break
    time.sleep(5)

# Step 3: fetch results
results = requests.get(
    f"https://graph.facebook.com/v21.0/{report_run_id}/insights",
    params={"access_token": TOKEN, "limit": 500}
).json()
```

## Batch Requests (fetch multiple accounts at once)

```python
batch = [
    {"method": "GET", "relative_url": f"act_{id}/insights?fields=impressions,spend&date_preset=yesterday&level=campaign"}
    for id in account_ids
]
r = requests.post(
    "https://graph.facebook.com/v21.0/",
    params={"access_token": TOKEN},
    data={"batch": json.dumps(batch)}
).json()
# r is a list of {code, body} — check code == 200 per item
```

Max 50 requests per batch call.