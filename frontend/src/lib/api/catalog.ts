import { FieldType } from "@/lib/platforms/types"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export async function fetchCatalog() {
    const res = await fetch(`${API_BASE}/api/catalog`)
    if (!res.ok) throw new Error(`GET /api/catalog → ${res.status}`)
    return res.json() // { version, count, connectors: [...] }
  }
  
  export async function fetchManifest(id: string) {
    const res = await fetch(`${API_BASE}/api/catalog/${id}`)
    if (!res.ok) throw new Error(`GET /api/catalog/${id} → ${res.status}`)
    return res.json() // manifest completo
  }
  
  export async function runIngestion(manifestId: string, params: Record<string, unknown>) {
    const res = await fetch(`${API_BASE}/api/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ manifest_id: manifestId, params }),
    })
    // Guardar X-Request-Id para debug
    const requestId = res.headers.get("X-Request-Id")
    const body = await res.json()
    if (!res.ok) throw Object.assign(new Error(body.reason ?? `HTTP ${res.status}`), { requestId, body })
    return { ...body, requestId }
  }

  export function bigqueryTypeToFieldType(t: string): FieldType {
    if (t === "STRING" || t === "BYTES" || t === "JSON" || t === "GEOGRAPHY" || t === "ARRAY" || t === "STRUCT") return "STRING"
    if (t === "INT64" || t === "INTEGER") return "INTEGER"
    if (t === "FLOAT64" || t === "NUMERIC" || t === "BIGNUMERIC" || t === "FLOAT") return "FLOAT"
    if (t === "BOOL" || t === "BOOLEAN") return "BOOLEAN"
    if (t === "DATE" || t === "DATETIME" || t === "TIMESTAMP" || t === "TIME") return "DATE"
    return "STRING" // fallback
  }