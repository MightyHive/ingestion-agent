/**
 * Build a minimal BigQuery CREATE TABLE DDL from editable column metadata.
 * Format aligns with mock / backend previews: `project.dataset.<tableName>`.
 */

export interface BigQueryDdlColumn {
  name: string
  type: string
  mode: "NULLABLE" | "REQUIRED"
  description?: string
}

export function buildBigQueryCreateDdl(
  tableName: string,
  columns: readonly BigQueryDdlColumn[]
): string {
  const tn = tableName.trim() || "pending_table"
  const lines = columns.map((c) => {
    const colName = c.name.trim() || "unnamed_field"
    const colType = c.type.trim() || "STRING"
    const tail = c.description?.trim() ? ` -- ${c.description.trim()}` : ""
    return `  ${colName} ${colType} ${c.mode}${tail}`
  })
  return [`CREATE TABLE \`project.dataset.${tn}\` (`, lines.join(",\n"), `);`].join("\n")
}
