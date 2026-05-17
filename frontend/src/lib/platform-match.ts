/** Normalize platform labels for matching templates ↔ credentials ↔ catalog. */
export function normalizePlatform(platform: string): string {
  return platform.trim().toLowerCase().replace(/\s+/g, "_")
}

const PLATFORM_ALIASES: Record<string, string> = {
  meta: "meta",
  facebook: "meta",
  meta_facebook: "meta",
  meta_facebook_ad_insights: "meta",
  tiktok: "tiktok",
  youtube: "youtube",
  google_ads: "google_ads",
  google: "google_ads",
  dv360: "dv360",
  cm360: "cm360",
}

/** Map manifest id / credential label to a canonical platform key. */
export function canonicalPlatform(platform: string): string {
  const n = normalizePlatform(platform)
  if (PLATFORM_ALIASES[n]) return PLATFORM_ALIASES[n]
  if (n.includes("facebook") || n.startsWith("meta")) return "meta"
  if (n.includes("tiktok")) return "tiktok"
  if (n.includes("youtube")) return "youtube"
  if (n.includes("google_ads") || n === "google") return "google_ads"
  return n
}

export function platformsCompatible(a: string, b: string): boolean {
  return canonicalPlatform(a) === canonicalPlatform(b)
}
