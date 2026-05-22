import { create } from "zustand"
import { persist, createJSONStorage } from "zustand/middleware"

/**
 * Active tenant ("client") for backend ingestion runs.
 *
 * Why this exists:
 *   The backend (`POST /api/run`) accepts an optional `tenant_id` that controls which entry of
 *   `~/.mds/tenants.json` is loaded (GCP project + service account + per-tenant context like
 *   `ad_account_id`) and which `{tenant_id}` token is substituted into the manifest's
 *   `bronze_pattern` (so the output table ends up named e.g.
 *   `bronze.meta_facebook_ad_insights_cliente1`).
 *
 * Source of the tenant list (MVP):
 *   `NEXT_PUBLIC_TENANTS` env, a comma-separated string ("dev,cliente1,cliente2"). The first
 *   entry is the default selection unless `NEXT_PUBLIC_DEFAULT_TENANT_ID` is set.
 *   Post-MVP this should be replaced by an authenticated `GET /api/tenants` endpoint.
 *
 * Persistence:
 *   The user's chosen tenant is stored in `localStorage` so it survives reloads.
 */

function parseTenantsEnv(raw: string | undefined): string[] {
  if (!raw) return []
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
}

const ENV_TENANTS = parseTenantsEnv(process.env.NEXT_PUBLIC_TENANTS)
const ENV_DEFAULT = process.env.NEXT_PUBLIC_DEFAULT_TENANT_ID?.trim()

/** Built-in fallback so the selector is never empty in dev. Real list comes from env. */
const DEFAULT_TENANTS: string[] = ENV_TENANTS.length > 0 ? ENV_TENANTS : ["dev", "cliente1"]
const DEFAULT_TENANT_ID: string =
  ENV_DEFAULT && DEFAULT_TENANTS.includes(ENV_DEFAULT) ? ENV_DEFAULT : DEFAULT_TENANTS[0]

interface TenantStore {
  /** All tenants the user can switch to (read-only for the MVP). */
  tenants: string[]
  /** Currently selected tenant — what gets sent to `POST /api/run`. */
  selectedTenantId: string
  setSelectedTenantId: (tenantId: string) => void
  /** Override the tenant list at runtime (used once `/api/tenants` exists). */
  setTenants: (tenants: string[]) => void
}

export const useTenantStore = create<TenantStore>()(
  persist(
    (set) => ({
      tenants: DEFAULT_TENANTS,
      selectedTenantId: DEFAULT_TENANT_ID,
      setSelectedTenantId: (tenantId) => set({ selectedTenantId: tenantId.trim() }),
      setTenants: (tenants) =>
        set((state) => {
          const clean = tenants.map((t) => t.trim()).filter((t) => t.length > 0)
          const next = clean.length > 0 ? clean : DEFAULT_TENANTS
          const selected = next.includes(state.selectedTenantId)
            ? state.selectedTenantId
            : next[0]
          return { tenants: next, selectedTenantId: selected }
        }),
    }),
    {
      name: "tenant-storage",
      storage: createJSONStorage(() =>
        typeof window !== "undefined"
          ? localStorage
          : { getItem: () => null, setItem: () => {}, removeItem: () => {} }
      ),
      // Persist only the user's choice. The list always re-reads env on boot so config changes propagate.
      partialize: (state) => ({ selectedTenantId: state.selectedTenantId }),
    }
  )
)

/** Read the current tenant outside React (used by export-ingestion). */
export function getActiveTenantId(): string {
  return useTenantStore.getState().selectedTenantId
}
