import type { Column } from "@/components/connectors/ColumnSelector"

/** Normalize final-event ``data`` from SSE into ``Column`` rows for the column picker. */
export function columnsFromUiTriggerData(data: Record<string, unknown> | undefined): Column[] {
  if (!data) return []
  const cols = data.columns
  if (Array.isArray(cols) && cols.length > 0) {
    const first = cols[0] as Record<string, unknown>
    if (first && typeof first.id === "string" && typeof first.name === "string") {
      return cols as Column[]
    }
  }
  const raw = data.available_fields
  if (!Array.isArray(raw)) return []
  return raw.map((name) => ({
    id: String(name),
    name: String(name),
    type: "STRING" as const,
    category: "structural",
  }))
}
