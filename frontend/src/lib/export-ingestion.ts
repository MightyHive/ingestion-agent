import { fetchCatalog, fetchManifest, runIngestion } from "@/lib/api/catalog"
import { buildDefaultRunParams } from "@/lib/manifest-default-params"
import type { CatalogConnector, Manifest } from "@/lib/stores/connectorStore"
import type { SavedTemplate } from "@/lib/stores/templateStore"
import { getActiveTenantId } from "@/lib/stores/tenantStore"

const IS_MOCK = process.env.NEXT_PUBLIC_MOCK === "true"

export interface TemplateRunResult {
  row_count: number
  target_table: string
  requestId: string | null
  errors: string[]
  columns: string[]
  rows_preview: Record<string, unknown>[]
}

export type TemplateRunMode = "refresh" | "backfill"

export interface TemplateRunOptions {
  mode: TemplateRunMode
  /** Used for Run now / scheduled refresh (days_back). */
  refreshWindowDays?: number
  /** ISO dates YYYY-MM-DD for backfill. */
  dateStart?: string
  dateEnd?: string
}

function fieldNamesFromTemplate(template: SavedTemplate): string[] {
  return template.columns.map((c) => c.original).filter(Boolean)
}

export async function resolveManifestId(template: SavedTemplate): Promise<string> {
  if (template.manifestId?.trim()) return template.manifestId.trim()

  const data = await fetchCatalog()
  const connectors = (data.connectors ?? []) as CatalogConnector[]
  const platform = template.platform.trim().toLowerCase()
  if (!platform) {
    throw new Error("Template has no platform; re-save it from Data Connection.")
  }

  const matches = connectors.filter(
    (c) =>
      c.platform?.toLowerCase() === platform ||
      c.id.toLowerCase().includes(platform.replace(/_/g, ""))
  )

  if (matches.length === 0) {
    throw new Error(`No catalog connector found for platform "${template.platform}".`)
  }
  if (matches.length === 1) return matches[0].id

  const facebook = matches.find((c) => c.id.includes("facebook"))
  if (facebook) return facebook.id

  return matches[0].id
}

/** Build params for POST /api/run from a saved template and run options. */
export function buildRunParamsFromTemplate(
  manifest: Manifest,
  template: SavedTemplate,
  options: TemplateRunOptions
): Record<string, unknown> {
  const fields = fieldNamesFromTemplate(template)
  const params: Record<string, unknown> = {
    ...buildDefaultRunParams(manifest),
    fields,
  }

  const clearWindowKeys = () => {
    delete params.days_back
    delete params.date_start
    delete params.date_stop
    delete params.since
    delete params.until
  }

  if (options.mode === "backfill") {
    if (!options.dateStart || !options.dateEnd) {
      throw new Error("Backfill requires start and end dates.")
    }
    clearWindowKeys()
    params.date_start = options.dateStart
    params.date_stop = options.dateEnd
    return params
  }

  const days = options.refreshWindowDays ?? 14
  clearWindowKeys()
  params.days_back = Math.min(90, Math.max(1, days))
  return params
}

export async function runTemplateIngestion(
  template: SavedTemplate,
  options: TemplateRunOptions
): Promise<TemplateRunResult> {
  if (IS_MOCK) {
    await new Promise((r) => setTimeout(r, 600))
    const fields = fieldNamesFromTemplate(template)
    return {
      row_count: 1200 + fields.length * 10,
      target_table: template.tableName,
      requestId: null,
      errors: [],
      columns: fields,
      rows_preview: fields.slice(0, 5).map((f, i) => ({ [f]: i + 1 })),
    }
  }

  const manifestId = await resolveManifestId(template)
  const manifest = (await fetchManifest(manifestId)) as Manifest
  const params = buildRunParamsFromTemplate(manifest, template, options)

  // Nivel 3: user-defined override (saved alongside the template) wins over backend default.
  const override = template.targetTableOverride?.trim()
  if (override) params.target_table = override

  const tenantId = getActiveTenantId()
  const body = await runIngestion(manifestId, params, tenantId)

  const errors = Array.isArray(body.errors) ? (body.errors as string[]) : []
  return {
    row_count: typeof body.row_count === "number" ? body.row_count : 0,
    target_table: typeof body.target_table === "string" ? body.target_table : template.tableName,
    requestId: body.requestId ?? null,
    errors,
    columns: Array.isArray(body.columns) ? (body.columns as string[]) : [],
    rows_preview: Array.isArray(body.rows_preview)
      ? (body.rows_preview as Record<string, unknown>[])
      : [],
  }
}
