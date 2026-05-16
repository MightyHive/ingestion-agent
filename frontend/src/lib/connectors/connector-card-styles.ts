/** Fallback badge when brand icon CDN fails or slug is unknown. */
export const CONNECTOR_CARD_STYLES: Record<string, { color: string; initial: string }> = {
  meta_facebook_ad_insights: { color: "#1877F2", initial: "F" },
  meta: { color: "#1877F2", initial: "M" },
  google_ads: { color: "#4285F4", initial: "G" },
  dv360: { color: "#34A853", initial: "D" },
  tiktok: { color: "#010101", initial: "T" },
  youtube: { color: "#FF0000", initial: "Y" },
}

export const DEFAULT_CONNECTOR_CARD_STYLE = { color: "#6366f1", initial: "?" }
