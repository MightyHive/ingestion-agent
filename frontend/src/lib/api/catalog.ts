import type { FieldType } from "@/lib/platforms/types"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export async function fetchCatalog() {
  const res = await fetch(`${API_BASE}/api/catalog`)
  if (!res.ok) throw new Error(`GET /api/catalog → ${res.status}`)
  return res.json() as Promise<{ version?: string; count?: number; connectors?: unknown[] }>
}

export async function fetchManifest(id: string) {
  const res = await fetch(`${API_BASE}/api/catalog/${encodeURIComponent(id)}`)
  if (!res.ok) throw new Error(`GET /api/catalog/${id} → ${res.status}`)
  return res.json()
}

/**
 * Calls `POST /api/run`.
 *
 * `tenantId` is optional. When omitted (or empty/whitespace) the backend falls back
 * to its `MDS_DEFAULT_TENANT_ID` (`"dev"`). When provided it controls:
 *   - which entry of `~/.mds/tenants.json` is loaded (GCP project, service account, context)
 *   - the `{tenant_id}` token substituted into the manifest's `bronze_pattern`
 *     (e.g. `bronze.meta_facebook_ad_insights_cliente1`)
 */
export async function runIngestion(
  manifestId: string,
  params: Record<string, unknown>,
  tenantId?: string | null,
  connectionId?: string | null
) {
  const trimmedTenant = tenantId?.trim() ? tenantId.trim() : undefined
  const trimmedConnection = connectionId?.trim() ? connectionId.trim() : undefined
  const requestBody: Record<string, unknown> = { manifest_id: manifestId, params }
  if (trimmedTenant) requestBody.tenant_id = trimmedTenant
  if (trimmedConnection) requestBody.connection_id = trimmedConnection

  const res = await fetch(`${API_BASE}/api/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(requestBody),
  })
  const body: Record<string, unknown> = await res.json()
  const headerRequestId = res.headers.get("X-Request-Id")
  const bodyRequestId = typeof body.request_id === "string" ? body.request_id : null
  const requestId = headerRequestId ?? bodyRequestId
  if (!res.ok) {
    const reason =
      typeof body.reason === "string"
        ? body.reason
        : typeof body.detail === "string"
          ? body.detail
          : typeof body.error === "string"
            ? body.error
            : `HTTP ${res.status}`
    throw Object.assign(new Error(reason), { requestId, body })
  }
  return { ...body, requestId } as Record<string, unknown> & { requestId: string | null }
}

/** Maps BigQuery / manifest scalar names to UI `FieldType` for column pickers. */
export function bigqueryTypeToFieldType(t: string): FieldType {
  if (t === "STRING" || t === "BYTES" || t === "JSON" || t === "GEOGRAPHY" || t === "ARRAY" || t === "STRUCT")
    return "STRING"
  if (t === "INT64" || t === "INTEGER") return "INTEGER"
  if (t === "FLOAT64" || t === "NUMERIC" || t === "BIGNUMERIC" || t === "FLOAT") return "FLOAT"
  if (t === "BOOL" || t === "BOOLEAN") return "BOOLEAN"
  if (t === "DATE" || t === "DATETIME" || t === "TIMESTAMP" || t === "TIME") return "DATE"
  return "STRING"
}
