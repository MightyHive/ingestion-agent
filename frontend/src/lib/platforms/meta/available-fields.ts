import type { FieldKind } from "@/lib/platforms/types"

/** Base metrics; API may return variants (e.g. real_impressions) resolved via `resolveMetaCanonicalId`. */
export const SHARED_METRICS: readonly string[] = [
  "impressions",
  "full_view_impressions",
  "full_view_reach",
  "reach",
  "spend",
  "clicks",
  "frequency",
  "cpm",
  "cpc",
  "cpp",
  "ctr",
  "video_p25_watched_actions",
  "video_p50_watched_actions",
  "video_p75_watched_actions",
  "video_p100_watched_actions",
  "video_play_actions",
  "actions",
  "conversions",
] as const

export const CAMPAIGN_OBJECT: readonly string[] = [
  "account_id",
  "account_name",
  "campaign_id",
  "campaign_name",
  "created_time",
  "objective",
] as const

export const ADSET_OBJECT: readonly string[] = ["adset_id", "adset_name"] as const

export const AD_OBJECT: readonly string[] = ["ad_id", "ad_name", "ad_click_actions"] as const

const METRIC_SET = new Set<string>(SHARED_METRICS)
const ALL_CAMPAIGN = [...CAMPAIGN_OBJECT, ...SHARED_METRICS] as const
const ALL_ADSET = [...CAMPAIGN_OBJECT, ...ADSET_OBJECT, ...SHARED_METRICS] as const
const ALL_AD = [...CAMPAIGN_OBJECT, ...ADSET_OBJECT, ...AD_OBJECT, ...SHARED_METRICS] as const

const CATALOG = new Set<string>(ALL_AD as unknown as string[])

const LEVELS = ["campaign", "adset", "ad"] as const
export type MetaLevel = (typeof LEVELS)[number]

/** Allowed `fields=` for each object level: union of object dimensions + shared metrics. */
export const AVAILABLE_FIELDS: Record<MetaLevel, readonly string[]> = {
  campaign: ALL_CAMPAIGN,
  adset: ALL_ADSET,
  ad: ALL_AD,
}

const AVAILABLE_BY_LEVEL: Record<MetaLevel, Set<string>> = {
  campaign: new Set(ALL_CAMPAIGN),
  adset: new Set(ALL_ADSET),
  ad: new Set(ALL_AD),
}

/** API id or legacy mock id -> canonical id from the lists above. */
const ID_ALIASES: Record<string, string> = {
  link_click_default_uas: "clicks",
  real_impressions: "impressions",
  real_impression: "impressions",
  link_clicks: "clicks",
  video_p25_watched_default_uas: "video_p25_watched_actions",
  video_p50_watched_default_uas: "video_p50_watched_actions",
  video_p75_watched_default_uas: "video_p75_watched_actions",
  video_p100_watched_default_uas: "video_p100_watched_actions",
  video_30_sec_watched_default_uas: "video_p100_watched_actions",
  campaign_objective: "objective",
  date_start: "created_time",
  inline_link_clicks: "clicks",
}

function tokenizeId(fieldId: string): string[] {
  return fieldId
    .toLowerCase()
    .split(/[._]+/)
    .filter((t) => t.length > 0)
}

/**
 * Map a platform field name to a canonical list key when possible (handles real_impressions, etc.).
 */
export function resolveMetaCanonicalId(fieldId: string): string {
  const raw = fieldId.toLowerCase().replace(/-/g, "_")
  if (ID_ALIASES[raw]) return ID_ALIASES[raw]
  if (METRIC_SET.has(raw) || CATALOG.has(raw)) return raw
  for (const pre of ["real_", "total_", "unique_", "gross_"]) {
    const stripped = raw.replace(new RegExp(`^${pre}`), "")
    if (METRIC_SET.has(stripped) || ID_ALIASES[stripped]) {
      return ID_ALIASES[stripped] ?? stripped
    }
  }
  for (const tok of tokenizeId(fieldId)) {
    if (METRIC_SET.has(tok) && !["click", "view"].includes(tok)) {
      if (["impressions", "clicks", "conversions", "spend", "reach"].includes(tok)) return tok
    }
    for (const m of SHARED_METRICS) {
      if (tok.length >= 4 && (m.includes(tok) || tok.includes(m)) && m.length / tok.length < 3) {
        if (raw === m || raw.includes(m) || m.includes(tok)) return m
      }
    }
  }
  if (raw.includes("impression") && (raw.startsWith("real_") || raw.includes("impressions"))) {
    return "impressions"
  }
  if (raw.includes("click") && (raw.includes("link") || raw.includes("uas") || raw.includes("inline"))) {
    return "clicks"
  }
  for (const m of SHARED_METRICS) {
    if (raw === m) return m
    if (raw.includes(`_${m}`) || raw.endsWith(`_${m}`) || raw.startsWith(`${m}_`)) return m
  }
  return raw
}

function kindForCanonical(canon: string): FieldKind {
  if (METRIC_SET.has(canon)) return "metric"
  if (canon === "ad_click_actions") return "metric"
  if (canon === "actions") return "metric"
  return "dimension"
}

/**
 * `endpoint` is the **first** (coarsest) of campaign → adset → ad in which the canonical
 * id appears. Shared metrics are listed at all levels, so their endpoint is `campaign`.
 * Unknown fields default to the finest level (ad) + dimension, so they are hidden at
 * coarser report levels by the parent filter.
 */
export function getMetaFieldEndpointAndKind(
  fieldId: string
): { endpoint: MetaLevel; kind: FieldKind; canonical: string } {
  const canonical = resolveMetaCanonicalId(fieldId)
  for (const level of LEVELS) {
    if (AVAILABLE_BY_LEVEL[level].has(canonical)) {
      return { endpoint: level, kind: kindForCanonical(canonical), canonical }
    }
  }
  if (isLikelyExtendedMetricFieldId(fieldId)) {
    return { endpoint: "ad", kind: "metric", canonical }
  }
  return { endpoint: "ad", kind: "dimension", canonical }
}

function isLikelyExtendedMetricFieldId(id: string): boolean {
  const s = id.toLowerCase()
  if (
    s.includes("conversion") ||
    (s.includes("click") && (s.includes("1d") || s.includes("7d") || s.includes("28d"))) ||
    s.includes("install") ||
    s.includes("purchase") ||
    s.includes("lead_") ||
    s.includes("pixel")
  ) {
    return true
  }
  return false
}

/** Catalog field: use AVAILABLE_FIELDS. Unknown API fields: only for `ad` (finest) report. */
export function isMetaFieldAllowedAtLevel(fieldId: string, level: MetaLevel): boolean {
  const c = resolveMetaCanonicalId(fieldId)
  if (CATALOG.has(c)) {
    return AVAILABLE_BY_LEVEL[level].has(c)
  }
  return level === "ad"
}

export function isCanonicalAllowedAtMetaLevel(canonical: string, level: MetaLevel): boolean {
  return AVAILABLE_BY_LEVEL[level].has(canonical)
}
