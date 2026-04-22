/**
 * Mock SSE for local dev without a backend. Replace with real `/api/chat` + SSE
 * when `NEXT_PUBLIC_MOCK` is not `"true"`.
 */
import type { FieldRow, FieldType } from "@/lib/platforms/types"
import { enrichFieldRowsForPlatform } from "@/lib/platforms/enrich"

// ── Raw field lists (id / label / type only); enrichment adds kind, endpoint, canonical. ─

type RawField = { id: string; name: string; type: FieldType }

const RAW_META: RawField[] = [
  { id: "impressions", name: "Impressions", type: "FLOAT" },
  { id: "link_click_default_uas", name: "Clicks", type: "FLOAT" },
  { id: "spend", name: "Cost", type: "FLOAT" },
  { id: "reach", name: "Reach", type: "FLOAT" },
  { id: "video_p25_watched_default_uas", name: "VideoViews 25%", type: "FLOAT" },
  { id: "video_p50_watched_default_uas", name: "VideoViews 50%", type: "FLOAT" },
  { id: "video_p75_watched_default_uas", name: "VideoViews 75%", type: "FLOAT" },
  { id: "video_p100_watched_default_uas", name: "VideoViews 100%", type: "FLOAT" },
  { id: "video_30_sec_watched_default_uas", name: "VideoViews 30sec", type: "FLOAT" },
  { id: "conversions", name: "Conversions (total)", type: "FLOAT" },
  { id: "app_custom_event.fb_mobile_purchase_1d_click", name: "In-app Purchase (1d click)", type: "FLOAT" },
  { id: "app_custom_event.fb_mobile_purchase_7d_click", name: "In-app Purchase (7d click)", type: "FLOAT" },
  { id: "app_custom_event.fb_mobile_purchase_28d_click", name: "In-app Purchase (28d click)", type: "FLOAT" },
  { id: "app_install_1d_click", name: "App Install (1d click)", type: "FLOAT" },
  { id: "app_install_7d_click", name: "App Install (7d click)", type: "FLOAT" },
  { id: "app_install_28d_click", name: "App Install (28d click)", type: "FLOAT" },
  { id: "landing_page_view_1d_click", name: "Landing Page View (1d click)", type: "FLOAT" },
  { id: "landing_page_view_7d_click", name: "Landing Page View (7d click)", type: "FLOAT" },
  { id: "lead_1d_click", name: "Lead (1d click)", type: "FLOAT" },
  { id: "lead_7d_click", name: "Lead (7d click)", type: "FLOAT" },
  { id: "lead_28d_click", name: "Lead (28d click)", type: "FLOAT" },
  { id: "offsite_conversion.fb_pixel_purchase_1d_click", name: "Purchase Pixel (1d click)", type: "FLOAT" },
  { id: "offsite_conversion.fb_pixel_purchase_7d_click", name: "Purchase Pixel (7d click)", type: "FLOAT" },
  { id: "offsite_conversion.fb_pixel_purchase_28d_click", name: "Purchase Pixel (28d click)", type: "FLOAT" },
  { id: "offsite_conversion.fb_pixel_add_to_cart_1d_click", name: "Add to Cart Pixel (1d click)", type: "FLOAT" },
  { id: "offsite_conversion.fb_pixel_add_to_cart_7d_click", name: "Add to Cart Pixel (7d click)", type: "FLOAT" },
  { id: "offsite_conversion.fb_pixel_initiate_checkout_1d_click", name: "Initiate Checkout Pixel (1d click)", type: "FLOAT" },
  { id: "offsite_conversion.fb_pixel_complete_registration_1d_click", name: "Complete Registration Pixel (1d click)", type: "FLOAT" },
  { id: "offsite_conversion.fb_pixel_lead_1d_click", name: "Lead Pixel (1d click)", type: "FLOAT" },
  { id: "offsite_conversion.fb_pixel_lead_7d_click", name: "Lead Pixel (7d click)", type: "FLOAT" },
  { id: "campaign_name", name: "Campaign", type: "STRING" },
  { id: "date_start", name: "Record Date", type: "DATE" },
  { id: "account_name", name: "Account", type: "STRING" },
  { id: "ad_id", name: "Ad ID", type: "STRING" },
  { id: "ad_name", name: "Ad Name", type: "STRING" },
  { id: "ad_status", name: "Ad Status", type: "STRING" },
  { id: "object_type", name: "Ad Type", type: "STRING" },
  { id: "adset_id", name: "Adset ID", type: "STRING" },
  { id: "adset_name", name: "Adset", type: "STRING" },
  { id: "adset_status", name: "Adset Status", type: "STRING" },
  { id: "campaign_id", name: "Channel Campaign ID", type: "STRING" },
  { id: "campaign_objective", name: "Campaign Objective", type: "STRING" },
  { id: "campaign_status", name: "Campaign Status", type: "STRING" },
  { id: "creative_id", name: "Creative ID", type: "STRING" },
  { id: "creative_name", name: "Creative Name", type: "STRING" },
  { id: "video_id", name: "Video ID", type: "STRING" },
  { id: "image_url", name: "Image URL", type: "STRING" },
  { id: "message", name: "Ad Text", type: "STRING" },
  { id: "title", name: "Title", type: "STRING" },
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

export function generateMockTemplate(connectorId: string, selectedIds: string[]) {
  const allFields = MOCK_FIELDS[connectorId] ?? []
  const selected  = allFields.filter(f => selectedIds.includes(f.id))

  const tableName = `raw_${connectorId}_ads`.replace("_analytics_ads", "_analytics")

  const columns = selected.map(f => ({
    name:        f.id.replace(/\./g, "_").replace(/-/g, "_"),
    original:    f.id,
    type:        BQ_TYPE[f.type] ?? "STRING",
    mode:        f.kind === "dimension" ? "REQUIRED" as const : "NULLABLE" as const,
    description: f.name,
  }))

  const ddl = [
    `CREATE TABLE \`project.dataset.${tableName}\` (`,
    columns.map(c =>
      `  ${c.name.padEnd(50)} ${c.type.padEnd(10)} ${c.mode}${c.description ? ` -- ${c.description}` : ""}`
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
