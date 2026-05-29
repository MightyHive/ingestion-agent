import type { FieldRow } from "@/lib/platforms/types"

const BQ_TYPE: Record<string, string> = {
  FLOAT: "FLOAT64",
  INTEGER: "INT64",
  STRING: "STRING",
  DATE: "DATE",
  BOOLEAN: "BOOL",
}

export type SchemaColumnRow = {
  name: string
  type: string
  mode: "NULLABLE" | "REQUIRED"
  description?: string
}

export function fieldRowToSchemaColumn(field: FieldRow): SchemaColumnRow {
  return {
    name: field.id.replace(/\./g, "_").replace(/-/g, "_"),
    type: BQ_TYPE[field.type] ?? "STRING",
    mode: field.kind === "dimension" ? "REQUIRED" : "NULLABLE",
    description: field.description ?? field.name,
  }
}

export function buildPreviewTableName(
  connectorId: string | null,
  reportingLevel: string | null
): string {
  const endpoint = reportingLevel ?? "all"
  return `raw_${connectorId ?? "connector"}_${endpoint}`
}
