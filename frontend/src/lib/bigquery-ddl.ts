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

function escapeSqlString(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')
}

export function buildBigQueryCreateDdl(
  tableName: string,
  columns: readonly BigQueryDdlColumn[],
  options?: { projectId?: string; dataset?: string }
): string {
  const projectId = options?.projectId?.trim() || "project"
  const dataset = options?.dataset?.trim() || "dataset"
  const tn = tableName.trim() || "pending_table"
  const lines = columns.map((c) => {
    const colName = c.name.trim() || "unnamed_field"
    const colType = c.type.trim() || "STRING"
    const description = c.description?.trim()
    const options = description ? ` OPTIONS(description="${escapeSqlString(description)}")` : ""
    return `  ${colName} ${colType} ${c.mode}${options}`
  })
  return [`CREATE TABLE \`${projectId}.${dataset}.${tn}\` (`, lines.join(",\n"), `);`].join("\n")
}
