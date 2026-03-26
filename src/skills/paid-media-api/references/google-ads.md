# Google Ads API — Deep Reference (Read-Only)

## GAQL — Useful Resources for Reporting

```sql
-- Resources to query:
FROM campaign
FROM ad_group
FROM video                      -- YouTube video ads
FROM customer
FROM geographic_view

-- Core metrics:
metrics.impressions, metrics.clicks, metrics.cost_micros,
metrics.conversions, metrics.conversions_value,
metrics.video_views, metrics.video_view_rate,
metrics.ctr, metrics.average_cpc, metrics.average_cpm, metrics.average_cpv

-- Dimensions:
campaign.id, campaign.name, campaign.status,
ad_group.id, ad_group.name

-- Segments (split by):
segments.date, segments.week, segments.month,
segments.device, segments.network, segments.ad_network_type
```

## MVP Read Query — Campaigns

```python
from google.ads.googleads.client import GoogleAdsClient

client = GoogleAdsClient.load_from_dict({
    "developer_token": "YOUR_DEV_TOKEN",
    "client_id": "YOUR_CLIENT_ID",
    "client_secret": "YOUR_CLIENT_SECRET",
    "refresh_token": "YOUR_REFRESH_TOKEN",
    "login_customer_id": "1234567890",
    "use_proto_plus": True,
})

ga_service = client.get_service("GoogleAdsService")
query = """
    SELECT
        campaign.id, campaign.name,
        metrics.impressions, metrics.clicks, metrics.cost_micros,
        metrics.ctr, metrics.conversions, metrics.video_views,
        segments.date
    FROM campaign
    WHERE segments.date DURING LAST_30_DAYS
    ORDER BY segments.date DESC
"""

response = ga_service.search_stream(customer_id="1234567890", query=query)
for batch in response:
    for row in batch.results:
        print(row.campaign.name, row.metrics.impressions,
              row.metrics.cost_micros / 1e6, row.segments.date)
```

## YouTube Video Ads Query

```python
query = """
    SELECT video.id, video.title,
        metrics.video_views, metrics.video_view_rate,
        metrics.impressions, metrics.cost_micros, metrics.average_cpv,
        segments.date
    FROM video
    WHERE segments.date DURING LAST_30_DAYS
"""
```

## Pagination

Use `search_stream` (preferred) — streams all results, no manual pagination needed.
If using `search`, loop on `next_page_token`:
```python
for page in ga_service.search(customer_id=ID, query=query).pages:
    for row in page.results:
        process(row)
```

## Error Handling

```python
from google.ads.googleads.errors import GoogleAdsException
try:
    for batch in ga_service.search_stream(customer_id=ID, query=query):
        for row in batch.results:
            process(row)
except GoogleAdsException as ex:
    for error in ex.failure.errors:
        print(f"{error.error_code} — {error.message}")
```

## Developer Token Levels
- **Test Account** → test accounts only, no live spend
- **Basic Access** → up to $5k/month managed spend
- **Standard Access** → no spend limit (requires application)

Apply at: Google Ads UI → Tools & Settings → API Center