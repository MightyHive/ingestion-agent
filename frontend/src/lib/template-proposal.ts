import type { FieldRow } from "@/lib/platforms/types"
import type { Manifest, TemplateColumn, TemplateProposal } from "@/lib/stores/connectorStore"

const BQ_FROM_FIELD_TYPE: Record<string, string> = {
  FLOAT: "FLOAT64",
  INTEGER: "INT64",
  STRING: "STRING",
  DATE: "DATE",
  BOOLEAN: "BOOL",
}

function sanitizeColumnName(fieldId: string): string {
  return fieldId.replace(/\./g, "_").replace(/-/g, "_")
}

function escapeSqlString(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')
}

/** Mirrors backend `_sanitise_bq_token`: lowercase, dashes/spaces → `_`, drop non-`[a-z0-9_]`. */
function sanitiseBqToken(value: string): string {
  const cleaned = value.trim().toLowerCase().replace(/-/g, "_").replace(/\s+/g, "_")
  return cleaned.replace(/[^a-z0-9_]/g, "")
}

function resolveTableName(
  manifest: Manifest | null,
  connectorId: string,
  reportingLevel: string | null,
  tenantId?: string | null
): string {
  const pattern = manifest?.table_naming?.bronze_pattern?.trim()
  if (pattern) {
    const id = manifest?.id ?? connectorId
    const platform = manifest?.platform ?? connectorId
    const tenant = sanitiseBqToken(tenantId ?? "")
    const substituted = pattern
      .replace(/\{id\}/g, id)
      .replace(/\{platform\}/g, platform)
      .replace(/\{connector\}/g, platform)
      .replace(/\{tenant_id\}/g, tenant)
    const segment = substituted.split(".").pop()?.trim()
    if (segment) return segment
  }
  const platformKey = (manifest?.platform ?? connectorId).replace(/\./g, "_")
  const level = reportingLevel?.trim() || "all"
  return `raw_${platformKey}_${level}`
}

function columnsFromFieldRows(selected: FieldRow[]): TemplateColumn[] {
  return selected.map((f) => ({
    name: sanitizeColumnName(f.id),
    original: f.id,
    type: BQ_FROM_FIELD_TYPE[f.type] ?? "STRING",
    mode: f.kind === "dimension" ? "REQUIRED" : "NULLABLE",
    description: f.description?.trim() || f.name,
  }))
}

function columnsFromManifestFields(
  manifest: Manifest,
  selectedIds: readonly string[]
): TemplateColumn[] {
  const selectedSet = new Set(selectedIds)
  return manifest.available_fields
    .filter((f) => selectedSet.has(f.name))
    .map((f) => ({
      name: sanitizeColumnName(f.name),
      original: f.name,
      type: f.type?.toUpperCase() || "STRING",
      mode: f.mode === "REQUIRED" ? "REQUIRED" : "NULLABLE",
      description: f.description?.trim() || f.name,
    }))
}

function buildReferenceDdl(tableName: string, columns: TemplateColumn[]): string {
  if (columns.length === 0) return ""
  return [
    `-- Reference schema only (not deployed from Data Connection)`,
    `CREATE TABLE \`project.dataset.${tableName}\` (`,
    columns
      .map(
        (c) =>
          `  ${c.name.padEnd(50)} ${c.type.padEnd(10)} ${c.mode}${
            c.description ? ` OPTIONS(description="${escapeSqlString(c.description)}")` : ""
          }`
      )
      .join(",\n"),
    `);`,
  ].join("\n")
}

export function buildTemplateProposalFromSelection(opts: {
  connectorId: string
  selectedIds: readonly string[]
  fields: readonly FieldRow[]
  manifest: Manifest | null
  reportingLevel?: string | null
  /** Active tenant — substituted into `{tenant_id}` in the manifest's `bronze_pattern`. */
  tenantId?: string | null
}): TemplateProposal {
  const {
    connectorId,
    selectedIds,
    fields,
    manifest,
    reportingLevel = null,
    tenantId = null,
  } = opts
  const idSet = new Set(selectedIds)
  const selectedFromRows = fields.filter((f) => idSet.has(f.id))

  const columns =
    selectedFromRows.length > 0
      ? columnsFromFieldRows(selectedFromRows)
      : manifest
        ? columnsFromManifestFields(manifest, selectedIds)
        : []

  if (columns.length === 0) {
    throw new Error("No matching fields for the current selection.")
  }

  const tableName = resolveTableName(manifest, connectorId, reportingLevel, tenantId)

  return {
    tableName,
    columns,
    ddl: buildReferenceDdl(tableName, columns),
  }
}
