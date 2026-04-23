import type { FieldRow } from "@/lib/platforms/types"
import { isPlatformId } from "@/lib/platforms/types"
import { enrichFieldRowsForPlatform } from "@/lib/platforms/enrich"

/**
 * Parse final-event `data` from SSE into `FieldRow` rows. Pass `platformId` so rows
 * are enriched (metric/dimension, endpoint) when the backend only sends `available_fields[]`.
 */
export function columnsFromUiTriggerData(
  data: Record<string, unknown> | undefined,
  platformId: string
): FieldRow[] {
  if (!data) return []
  const pid = isPlatformId(platformId) ? platformId : "meta"
  const cols = data.columns
  if (Array.isArray(cols) && cols.length > 0) {
    const first = cols[0] as Record<string, unknown>
    if (first && typeof first.id === "string" && typeof first.name === "string") {
      const asIncoming = (cols as Record<string, unknown>[]).map((c) => ({
        id: String(c.id),
        name: String(c.name),
        type: (typeof c.type === "string" ? c.type : "STRING") as FieldRow["type"],
        kind: c.kind as FieldRow["kind"] | undefined,
        endpoint: typeof c.endpoint === "string" ? c.endpoint : undefined,
        description: typeof c.description === "string" ? c.description : undefined,
        category: typeof c.category === "string" ? c.category : undefined,
      }))
      return enrichFieldRowsForPlatform(pid, asIncoming)
    }
  }
  const raw = data.available_fields
  if (!Array.isArray(raw)) return []
  return enrichFieldRowsForPlatform(
    pid,
    raw.map((name) => ({
      id: String(name),
      name: String(name),
      type: "STRING" as const,
    }))
  )
}
