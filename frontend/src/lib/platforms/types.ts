/**
 * Single backend-aligned contract for Data Connection field pickers and reports.
 * Add a new `PlatformId` in PLATFORM_IDS, then register tabs + enrich rules in
 * `lib/platforms/registry.ts` and (when needed) `lib/platforms/<platform>/`.
 */
export const PLATFORM_IDS = [
  "meta",
  "tiktok",
  "youtube",
  "google_ads",
  "dv360",
] as const

export type PlatformId = (typeof PLATFORM_IDS)[number]

export function isPlatformId(s: string): s is PlatformId {
  return (PLATFORM_IDS as readonly string[]).includes(s)
}

/** Distinguish measurable KPIs from attributes / join keys. */
export type FieldKind = "metric" | "dimension"

export type FieldType = "STRING" | "INTEGER" | "FLOAT" | "DATE" | "BOOLEAN"

/**
 * `endpoint` is the **coarsest** reporting object where the field is listed in the
 * platform catalog (e.g. Meta: campaign, adset, ad). Use `filterFieldsByReportingLevel`
 * (parent) to enforce valid granularity; `Column` tabs can further group dimensions.
 * Metrics with the same min level may be shown in every filter tab in the UI (see
 * `ColumnSelector`).
 */
export type FieldRow = {
  id: string
  name: string
  type: FieldType
  kind: FieldKind
  endpoint: string
  description?: string
  /**
   * Canonical name after resolving platform aliases (e.g. real_impressions → impressions).
   * Omitted if unknown; backend may still send a stable `id` only.
   */
  canonicalId?: string
}

export type ReportEndpoint = {
  id: string
  label: string
}
