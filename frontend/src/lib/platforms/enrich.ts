import type { FieldKind, FieldRow, FieldType, PlatformId } from "@/lib/platforms/types"
import { isPlatformId } from "@/lib/platforms/types"
import { getMetaFieldEndpointAndKind } from "@/lib/platforms/meta/available-fields"
import { getReportEndpoints } from "@/lib/platforms/registry"

type IncomingRow = {
  id: string
  name: string
  type: FieldType
  kind?: FieldKind
  endpoint?: string
  description?: string
  canonicalId?: string
  /** @deprecated use kind + endpoint; accepted from legacy payloads */
  category?: string
}

const DEFAULT_TYPE: FieldType = "STRING"

function normalizeType(t: unknown): FieldType {
  if (t === "STRING" || t === "INTEGER" || t === "FLOAT" || t === "DATE" || t === "BOOLEAN")
    return t
  return DEFAULT_TYPE
}

function firstEndpointId(platform: PlatformId): string {
  const tabs = getReportEndpoints(platform)
  return tabs[0]?.id ?? "campaign"
}

function defaultKindForNonMeta(t: FieldType, id: string): FieldRow["kind"] {
  const s = id.toLowerCase()
  if (s.includes("cost") || s.includes("spend") || s === "impressions" || s.includes("click"))
    return "metric"
  if (t === "FLOAT" || t === "INTEGER") return "metric"
  return "dimension"
}

/**
 * Normalizes API / SSE / mock field rows to `FieldRow`. Idempotent if `kind` + `endpoint` present.
 */
export function enrichFieldRowsForPlatform(
  platformId: string,
  rows: readonly IncomingRow[]
): FieldRow[] {
  const pid: PlatformId = isPlatformId(platformId) ? platformId : "meta"
  return rows.map((r) => enrichOne(pid, r))
}

function enrichOne(platform: PlatformId, r: IncomingRow): FieldRow {
  const t = normalizeType(r.type)
  if (r.kind && r.endpoint) {
    return {
      id: r.id,
      name: r.name,
      type: t,
      kind: r.kind,
      endpoint: r.endpoint,
      description: r.description,
      canonicalId: r.canonicalId ?? r.id,
    }
  }
  if (platform === "meta") {
    const m = getMetaFieldEndpointAndKind(r.id)
    return {
      id: r.id,
      name: r.name,
      type: t,
      kind: m.kind,
      endpoint: m.endpoint,
      description: r.description,
      canonicalId: m.canonical,
    }
  }
  return {
    id: r.id,
    name: r.name,
    type: t,
    kind: defaultKindForNonMeta(t, r.id),
    endpoint: firstEndpointId(platform),
    description: r.description,
  }
}
