const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export interface BackendConnection {
  connection_id: string
  tenant_id: string
  provider: string
  secret_id: string
  status: string
  name: string | null
  created_at: string
  updated_at: string
}

function encodeName(name: string, brand: string, market: string): string {
  return JSON.stringify({ n: name, b: brand, m: market })
}

export function decodeName(backendName: string | null): { name: string; brand: string; market: string } {
  if (!backendName) return { name: "", brand: "", market: "" }
  try {
    const parsed = JSON.parse(backendName)
    return { name: parsed.n ?? backendName, brand: parsed.b ?? "", market: parsed.m ?? "" }
  } catch {
    return { name: backendName, brand: "", market: "" }
  }
}

function headers(tenantId: string) {
  return { "Content-Type": "application/json", "X-Tenant-Id": tenantId }
}

export async function fetchCredentials(tenantId: string): Promise<BackendConnection[]> {
  const res = await fetch(`${API_BASE}/api/credentials`, {
    headers: { "X-Tenant-Id": tenantId },
  })
  if (!res.ok) throw new Error(`GET /api/credentials → ${res.status}`)
  const body = await res.json()
  return body.connections as BackendConnection[]
}

export async function saveCredential(
  connectionId: string,
  provider: string,
  payload: Record<string, string>,
  name: string,
  brand: string,
  market: string,
  tenantId: string,
): Promise<BackendConnection> {
  const res = await fetch(
    `${API_BASE}/api/credentials/${encodeURIComponent(provider)}/${encodeURIComponent(connectionId)}`,
    {
      method: "PUT",
      headers: headers(tenantId),
      body: JSON.stringify({
        payload,
        name: encodeName(name, brand, market),
      }),
    },
  )
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { reason?: string }).reason ?? `PUT /api/credentials → ${res.status}`)
  }
  const body = await res.json()
  return (body as { connection: BackendConnection }).connection
}

export async function deactivateCredential(connectionId: string, tenantId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/credentials/${encodeURIComponent(connectionId)}/status`,
    {
      method: "PATCH",
      headers: headers(tenantId),
      body: JSON.stringify({ status: "inactive" }),
    },
  )
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { reason?: string }).reason ?? `PATCH /api/credentials → ${res.status}`)
  }
}
