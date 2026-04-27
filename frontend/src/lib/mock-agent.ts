/**
 * Mock SSE for local dev without a backend. Replace with real `/api/chat` + SSE
 * when `NEXT_PUBLIC_MOCK` is not `"true"`.
 */
import type { FieldRow, FieldType } from "@/lib/platforms/types"
import { enrichFieldRowsForPlatform } from "@/lib/platforms/enrich"

// ── Raw field lists (id / label / type only); enrichment adds kind, endpoint, canonical. ─

type RawField = { id: string; name: string; type: FieldType; description?: string }

const RAW_META: RawField[] = [
  { id: "impressions", name: "Impressions", type: "FLOAT", description: "Total number of times your ads were on screen." },
  { id: "link_click_default_uas", name: "Clicks", type: "FLOAT", description: "Number of clicks on links within the ad that led to advertiser-specified destinations, on or off Meta." },
  { id: "spend", name: "Cost", type: "FLOAT", description: "The total amount spent to show your ads during the reporting period." },
  { id: "reach", name: "Reach", type: "FLOAT", description: "Number of unique accounts that saw your ads at least once." },
  { id: "video_p25_watched_default_uas", name: "VideoViews 25%", type: "FLOAT", description: "Number of times your video was watched to 25% of its length, including watches that skipped ahead." },
  { id: "video_p50_watched_default_uas", name: "VideoViews 50%", type: "FLOAT", description: "Number of times your video was watched to 50% of its length, including watches that skipped ahead." },
  { id: "video_p75_watched_default_uas", name: "VideoViews 75%", type: "FLOAT", description: "Number of times your video was watched to 75% of its length, including watches that skipped ahead." },
  { id: "video_p100_watched_default_uas", name: "VideoViews 100%", type: "FLOAT", description: "Number of times your video was watched to completion, including watches that skipped ahead to this point." },
  { id: "video_30_sec_watched_default_uas", name: "VideoViews 30sec", type: "FLOAT", description: "Number of times your video was watched for at least 30 seconds, or for nearly its total length if it's shorter than 30 seconds." },
  { id: "conversions", name: "Conversions (total)", type: "FLOAT", description: "Total number of conversion events attributed to your ads across all Meta Pixel, app, and on-Facebook conversion windows." },
  { id: "app_custom_event.fb_mobile_purchase_1d_click", name: "In-app Purchase (1d click)", type: "FLOAT", description: "In-app purchase events attributed to a click on your ad within 1 day." },
  { id: "app_custom_event.fb_mobile_purchase_7d_click", name: "In-app Purchase (7d click)", type: "FLOAT", description: "In-app purchase events attributed to a click on your ad within 7 days." },
  { id: "app_custom_event.fb_mobile_purchase_28d_click", name: "In-app Purchase (28d click)", type: "FLOAT", description: "In-app purchase events attributed to a click on your ad within 28 days." },
  { id: "app_install_1d_click", name: "App Install (1d click)", type: "FLOAT", description: "Mobile app installs attributed to a click on your ad within 1 day." },
  { id: "app_install_7d_click", name: "App Install (7d click)", type: "FLOAT", description: "Mobile app installs attributed to a click on your ad within 7 days." },
  { id: "app_install_28d_click", name: "App Install (28d click)", type: "FLOAT", description: "Mobile app installs attributed to a click on your ad within 28 days." },
  { id: "landing_page_view_1d_click", name: "Landing Page View (1d click)", type: "FLOAT", description: "Number of times a person clicked your ad and successfully loaded the destination URL within 1 day." },
  { id: "landing_page_view_7d_click", name: "Landing Page View (7d click)", type: "FLOAT", description: "Number of times a person clicked your ad and successfully loaded the destination URL within 7 days." },
  { id: "lead_1d_click", name: "Lead (1d click)", type: "FLOAT", description: "Number of lead events attributed to a click on your ad within 1 day (on-Facebook forms, Messenger, or Instagram)." },
  { id: "lead_7d_click", name: "Lead (7d click)", type: "FLOAT", description: "Number of lead events attributed to a click on your ad within 7 days." },
  { id: "lead_28d_click", name: "Lead (28d click)", type: "FLOAT", description: "Number of lead events attributed to a click on your ad within 28 days." },
  { id: "offsite_conversion.fb_pixel_purchase_1d_click", name: "Purchase Pixel (1d click)", type: "FLOAT", description: "Website purchases tracked by Meta Pixel and attributed to a click on your ad within 1 day." },
  { id: "offsite_conversion.fb_pixel_purchase_7d_click", name: "Purchase Pixel (7d click)", type: "FLOAT", description: "Website purchases tracked by Meta Pixel and attributed to a click on your ad within 7 days." },
  { id: "offsite_conversion.fb_pixel_purchase_28d_click", name: "Purchase Pixel (28d click)", type: "FLOAT", description: "Website purchases tracked by Meta Pixel and attributed to a click on your ad within 28 days." },
  { id: "offsite_conversion.fb_pixel_add_to_cart_1d_click", name: "Add to Cart Pixel (1d click)", type: "FLOAT", description: "Add-to-cart events tracked by Meta Pixel and attributed to a click on your ad within 1 day." },
  { id: "offsite_conversion.fb_pixel_add_to_cart_7d_click", name: "Add to Cart Pixel (7d click)", type: "FLOAT", description: "Add-to-cart events tracked by Meta Pixel and attributed to a click on your ad within 7 days." },
  { id: "offsite_conversion.fb_pixel_initiate_checkout_1d_click", name: "Initiate Checkout Pixel (1d click)", type: "FLOAT", description: "Checkout initiations tracked by Meta Pixel and attributed to a click on your ad within 1 day." },
  { id: "offsite_conversion.fb_pixel_complete_registration_1d_click", name: "Complete Registration Pixel (1d click)", type: "FLOAT", description: "Registration completions tracked by Meta Pixel and attributed to a click on your ad within 1 day." },
  { id: "offsite_conversion.fb_pixel_lead_1d_click", name: "Lead Pixel (1d click)", type: "FLOAT", description: "Lead events tracked by Meta Pixel and attributed to a click on your ad within 1 day." },
  { id: "offsite_conversion.fb_pixel_lead_7d_click", name: "Lead Pixel (7d click)", type: "FLOAT", description: "Lead events tracked by Meta Pixel and attributed to a click on your ad within 7 days." },
  { id: "campaign_name", name: "Campaign", type: "STRING", description: "Name of the campaign the ad belongs to." },
  { id: "date_start", name: "Record Date", type: "DATE", description: "The start date of the reporting period." },
  { id: "account_name", name: "Account", type: "STRING", description: "Name of the Meta Ads account." },
  { id: "ad_id", name: "Ad ID", type: "STRING", description: "Unique identifier for the ad." },
  { id: "ad_name", name: "Ad Name", type: "STRING", description: "Name of the ad as set in Ads Manager." },
  { id: "ad_status", name: "Ad Status", type: "STRING", description: "Delivery status of the ad (e.g. ACTIVE, PAUSED, DISAPPROVED)." },
  { id: "object_type", name: "Ad Type", type: "STRING", description: "Type of the ad object (e.g. VIDEO, LINK, PAGE_LIKE)." },
  { id: "adset_id", name: "Adset ID", type: "STRING", description: "Unique identifier for the ad set." },
  { id: "adset_name", name: "Adset", type: "STRING", description: "Name of the ad set." },
  { id: "adset_status", name: "Adset Status", type: "STRING", description: "Delivery status of the ad set (e.g. ACTIVE, PAUSED)." },
  { id: "campaign_id", name: "Channel Campaign ID", type: "STRING", description: "Unique identifier for the campaign in the Meta Ads platform." },
  { id: "campaign_objective", name: "Campaign Objective", type: "STRING", description: "Marketing objective of the campaign (e.g. CONVERSIONS, REACH, TRAFFIC)." },
  { id: "campaign_status", name: "Campaign Status", type: "STRING", description: "Delivery status of the campaign (e.g. ACTIVE, PAUSED, ARCHIVED)." },
  { id: "creative_id", name: "Creative ID", type: "STRING", description: "Unique identifier for the ad creative." },
  { id: "creative_name", name: "Creative Name", type: "STRING", description: "Name of the ad creative." },
  { id: "video_id", name: "Video ID", type: "STRING", description: "Unique identifier for the video asset used in the ad." },
  { id: "image_url", name: "Image URL", type: "STRING", description: "URL of the image used in the ad creative." },
  { id: "message", name: "Ad Text", type: "STRING", description: "Primary text body of the ad." },
  { id: "title", name: "Title", type: "STRING", description: "Headline of the ad creative." },
]

const RAW_TIKTOK: RawField[] = [
  { id: "ad_group_id", name: "Ad Group ID", type: "STRING" },
  { id: "campaign_name", name: "Campaign Name", type: "STRING" },
  { id: "cost_cash", name: "Cost", type: "FLOAT" },
  { id: "impressions", name: "Impressions", type: "INTEGER" },
  { id: "clicks", name: "Clicks", type: "INTEGER" },
  { id: "video_play_rate", name: "Video Play Rate", type: "FLOAT" },
  { id: "conversions", name: "Conversions", type: "INTEGER" },
  { id: "date", name: "Date", type: "DATE" },
]

const RAW_YOUTUBE: RawField[] = [
  { id: "video_id", name: "Video ID", type: "STRING" },
  { id: "channel_id", name: "Channel ID", type: "STRING" },
  { id: "views", name: "Views", type: "INTEGER" },
  { id: "watch_time_minutes", name: "Watch Time (min)", type: "FLOAT" },
  { id: "likes", name: "Likes", type: "INTEGER" },
  { id: "comments", name: "Comments", type: "INTEGER" },
  { id: "estimated_revenue", name: "Revenue", type: "FLOAT" },
  { id: "date", name: "Date", type: "DATE" },
]

export const MOCK_FIELDS: Record<string, FieldRow[]> = {
  meta: enrichFieldRowsForPlatform("meta", RAW_META),
  tiktok: enrichFieldRowsForPlatform("tiktok", RAW_TIKTOK),
  youtube: enrichFieldRowsForPlatform("youtube", RAW_YOUTUBE),
}

// ── Mock schema proposal (Data Architect) ─────────────────────────────

const BQ_TYPE: Record<string, string> = {
  FLOAT:   "FLOAT64",
  INTEGER: "INT64",
  STRING:  "STRING",
  DATE:    "DATE",
  BOOLEAN: "BOOL",
}

function escapeSqlString(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')
}

export function generateMockTemplate(connectorId: string, selectedIds: string[], reportingLevel?: string | null) {
  const allFields = MOCK_FIELDS[connectorId] ?? []
  const selected  = allFields.filter(f => selectedIds.includes(f.id))

  const endpoint = reportingLevel ?? "all"
  const tableName = `raw_${connectorId}_${endpoint}`

  const columns = selected.map(f => ({
    name:        f.id.replace(/\./g, "_").replace(/-/g, "_"),
    original:    f.id,
    type:        BQ_TYPE[f.type] ?? "STRING",
    mode:        f.kind === "dimension" ? "REQUIRED" as const : "NULLABLE" as const,
    description: f.description ?? f.name,
  }))

  const ddl = [
    `CREATE TABLE \`project.dataset.${tableName}\` (`,
    columns.map(c =>
      `  ${c.name.padEnd(50)} ${c.type.padEnd(10)} ${c.mode}${c.description ? ` OPTIONS(description="${escapeSqlString(c.description)}")` : ""}`
    ).join(",\n"),
    `);`,
  ].join("\n")

  return { tableName, columns, ddl }
}

// ── Mock SSE stream (same shape as expected FastAPI SSE) ──────────

export async function* mockAgentStream(connectorId: string): AsyncGenerator<string> {
  const delay = (ms: number) => new Promise(r => setTimeout(r, ms))

  yield `data: ${JSON.stringify({ type: "connection", status: "connected" })}\n\n`
  await delay(400)

  yield `data: ${JSON.stringify({ type: "progress", node: "coordinator" })}\n\n`
  await delay(1200)

  yield `data: ${JSON.stringify({ type: "progress", node: "api_researcher" })}\n\n`
  await delay(1500)

  const columns = MOCK_FIELDS[connectorId] ?? []

  yield `data: ${JSON.stringify({
    type: "final",
    response_text: `I inspected the API. There are ${columns.length} available fields. Select which ones to extract.`,
    requires_human_input: true,
    ui_trigger: {
      component: "ColumnSelector",
      message: `Select ${connectorId === "meta" ? "Meta Ads" : connectorId === "tiktok" ? "TikTok Ads" : "YouTube"} fields to extract`,
      data: { columns },
    },
  })}\n\n`
}

export async function* mockSubmitInputStream(
  connectorId: string,
  selectedIds: string[]
): AsyncGenerator<string> {
  const delay = (ms: number) => new Promise((r) => setTimeout(r, ms))
  const proposal = generateMockTemplate(connectorId, selectedIds)

  yield `data: ${JSON.stringify({ type: "connection", status: "connected" })}\n\n`
  await delay(300)

  yield `data: ${JSON.stringify({ type: "progress", node: "coordinator" })}\n\n`
  await delay(400)

  yield `data: ${JSON.stringify({ type: "progress", node: "data_architect" })}\n\n`
  await delay(600)

  yield `data: ${JSON.stringify({
    type: "final",
    response_text: "Template proposal is ready to review.",
    ui_trigger: {
      component: "TemplateApproval",
      message: "Review the proposed DDL.",
      data: {
        ddl: proposal.ddl,
        columns: proposal.columns,
        tableName: proposal.tableName,
      },
    },
  })}\n\n`
}
