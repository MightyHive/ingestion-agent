/**
 * Mock SSE responses para desarrollo local sin backend.
 * Cuando el back esté listo, esto se ignora automáticamente.
 * 
 * Los campos de Meta son los reales devueltos por el API Researcher.
 */

export interface Column {
  id: string
  name: string
  type: "STRING" | "FLOAT" | "INTEGER" | "DATE" | "BOOLEAN"
  category: "performance" | "conversion" | "structural"
}

// ── Campos reales de Meta Ads (API Researcher output) ─────────────────────────

export const META_FIELDS: Column[] = [
  // Performance
  { id: "impressions", name: "Impressions", type: "FLOAT", category: "performance" },
  { id: "link_click_default_uas", name: "Clicks", type: "FLOAT", category: "performance" },
  { id: "spend", name: "Cost", type: "FLOAT", category: "performance" },
  { id: "reach", name: "Reach", type: "FLOAT", category: "performance" },
  { id: "video_p25_watched_default_uas", name: "VideoViews 25%", type: "FLOAT", category: "performance" },
  { id: "video_p50_watched_default_uas", name: "VideoViews 50%", type: "FLOAT", category: "performance" },
  { id: "video_p75_watched_default_uas", name: "VideoViews 75%", type: "FLOAT", category: "performance" },
  { id: "video_p100_watched_default_uas", name: "VideoViews 100%", type: "FLOAT", category: "performance" },
  { id: "video_30_sec_watched_default_uas", name: "VideoViews 30sec", type: "FLOAT", category: "performance" },

  // Conversions
  { id: "conversions", name: "Conversions (total)", type: "FLOAT", category: "conversion" },
  { id: "app_custom_event.fb_mobile_purchase_1d_click", name: "In-app Purchase (1d click)", type: "FLOAT", category: "conversion" },
  { id: "app_custom_event.fb_mobile_purchase_7d_click", name: "In-app Purchase (7d click)", type: "FLOAT", category: "conversion" },
  { id: "app_custom_event.fb_mobile_purchase_28d_click", name: "In-app Purchase (28d click)", type: "FLOAT", category: "conversion" },
  { id: "app_install_1d_click", name: "App Install (1d click)", type: "FLOAT", category: "conversion" },
  { id: "app_install_7d_click", name: "App Install (7d click)", type: "FLOAT", category: "conversion" },
  { id: "app_install_28d_click", name: "App Install (28d click)", type: "FLOAT", category: "conversion" },
  { id: "landing_page_view_1d_click", name: "Landing Page View (1d click)", type: "FLOAT", category: "conversion" },
  { id: "landing_page_view_7d_click", name: "Landing Page View (7d click)", type: "FLOAT", category: "conversion" },
  { id: "lead_1d_click", name: "Lead (1d click)", type: "FLOAT", category: "conversion" },
  { id: "lead_7d_click", name: "Lead (7d click)", type: "FLOAT", category: "conversion" },
  { id: "lead_28d_click", name: "Lead (28d click)", type: "FLOAT", category: "conversion" },
  { id: "offsite_conversion.fb_pixel_purchase_1d_click", name: "Purchase Pixel (1d click)", type: "FLOAT", category: "conversion" },
  { id: "offsite_conversion.fb_pixel_purchase_7d_click", name: "Purchase Pixel (7d click)", type: "FLOAT", category: "conversion" },
  { id: "offsite_conversion.fb_pixel_purchase_28d_click", name: "Purchase Pixel (28d click)", type: "FLOAT", category: "conversion" },
  { id: "offsite_conversion.fb_pixel_add_to_cart_1d_click", name: "Add to Cart Pixel (1d click)", type: "FLOAT", category: "conversion" },
  { id: "offsite_conversion.fb_pixel_add_to_cart_7d_click", name: "Add to Cart Pixel (7d click)", type: "FLOAT", category: "conversion" },
  { id: "offsite_conversion.fb_pixel_initiate_checkout_1d_click", name: "Initiate Checkout Pixel (1d click)", type: "FLOAT", category: "conversion" },
  { id: "offsite_conversion.fb_pixel_complete_registration_1d_click", name: "Complete Registration Pixel (1d click)", type: "FLOAT", category: "conversion" },
  { id: "offsite_conversion.fb_pixel_lead_1d_click", name: "Lead Pixel (1d click)", type: "FLOAT", category: "conversion" },
  { id: "offsite_conversion.fb_pixel_lead_7d_click", name: "Lead Pixel (7d click)", type: "FLOAT", category: "conversion" },

  // Structural
  { id: "campaign_name", name: "Campaign", type: "STRING", category: "structural" },
  { id: "date_start", name: "Record Date", type: "DATE", category: "structural" },
  { id: "account_name", name: "Account", type: "STRING", category: "structural" },
  { id: "ad_id", name: "Ad ID", type: "STRING", category: "structural" },
  { id: "ad_name", name: "Ad Name", type: "STRING", category: "structural" },
  { id: "ad_status", name: "Ad Status", type: "STRING", category: "structural" },
  { id: "object_type", name: "Ad Type", type: "STRING", category: "structural" },
  { id: "adset_id", name: "Adset ID", type: "STRING", category: "structural" },
  { id: "adset_name", name: "Adset", type: "STRING", category: "structural" },
  { id: "adset_status", name: "Adset Status", type: "STRING", category: "structural" },
  { id: "campaign_id", name: "Channel Campaign ID", type: "STRING", category: "structural" },
  { id: "campaign_objective", name: "Campaign Objective", type: "STRING", category: "structural" },
  { id: "campaign_status", name: "Campaign Status", type: "STRING", category: "structural" },
  { id: "creative_id", name: "Creative ID", type: "STRING", category: "structural" },
  { id: "creative_name", name: "Creative Name", type: "STRING", category: "structural" },
  { id: "video_id", name: "Video ID", type: "STRING", category: "structural" },
  { id: "image_url", name: "Image URL", type: "STRING", category: "structural" },
  { id: "message", name: "Ad Text", type: "STRING", category: "structural" },
  { id: "title", name: "Title", type: "STRING", category: "structural" },
]

// ── Campos por conector (TikTok y YouTube son placeholders por ahora) ─────────

export const MOCK_FIELDS: Record<string, Column[]> = {
  meta: META_FIELDS,
  tiktok: [
    { id: "ad_group_id", name: "Ad Group ID", type: "STRING", category: "structural" },
    { id: "campaign_name", name: "Campaign Name", type: "STRING", category: "structural" },
    { id: "cost_cash", name: "Cost", type: "FLOAT", category: "performance" },
    { id: "impressions", name: "Impressions", type: "INTEGER", category: "performance" },
    { id: "clicks", name: "Clicks", type: "INTEGER", category: "performance" },
    { id: "video_play_rate", name: "Video Play Rate", type: "FLOAT", category: "performance" },
    { id: "conversions", name: "Conversions", type: "INTEGER", category: "conversion" },
    { id: "date", name: "Date", type: "DATE", category: "structural" },
  ],
  youtube: [
    { id: "video_id", name: "Video ID", type: "STRING", category: "structural" },
    { id: "channel_id", name: "Channel ID", type: "STRING", category: "structural" },
    { id: "views", name: "Views", type: "INTEGER", category: "performance" },
    { id: "watch_time_minutes", name: "Watch Time (min)", type: "FLOAT", category: "performance" },
    { id: "likes", name: "Likes", type: "INTEGER", category: "performance" },
    { id: "comments", name: "Comments", type: "INTEGER", category: "performance" },
    { id: "estimated_revenue", name: "Revenue", type: "FLOAT", category: "performance" },
    { id: "date", name: "Date", type: "DATE", category: "structural" },
  ],
}

// ── Mock schema proposal (simula la respuesta del Data Architect) ─────────────

const BQ_TYPE: Record<string, string> = {
  FLOAT:   "FLOAT64",
  INTEGER: "INT64",
  STRING:  "STRING",
  DATE:    "DATE",
  BOOLEAN: "BOOL",
}

export function generateMockSchema(connectorId: string, selectedIds: string[]) {
  const allFields = MOCK_FIELDS[connectorId] ?? []
  const selected  = allFields.filter(f => selectedIds.includes(f.id))

  const tableName = `raw_${connectorId}_ads`.replace("_analytics_ads", "_analytics")

  const columns = selected.map(f => ({
    name:        f.id.replace(/\./g, "_").replace(/-/g, "_"),
    original:    f.id,
    type:        BQ_TYPE[f.type] ?? "STRING",
    mode:        f.category === "structural" ? "REQUIRED" : "NULLABLE" as "REQUIRED" | "NULLABLE",
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

// ── Mock SSE stream (simula lo que mandará el back cuando esté listo) ─────────

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
    response_text: `Investigué la API. Encontré ${columns.length} campos disponibles. Seleccioná los que querés extraer.`,
    requires_human_input: true,
    ui_trigger: {
      component: "ColumnSelector",
      message: `Seleccioná los campos de ${connectorId === "meta" ? "Meta Ads" : connectorId === "tiktok" ? "TikTok Ads" : "YouTube Analytics"}`,
      data: { columns },
    },
  })}\n\n`
}
