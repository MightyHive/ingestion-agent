"use client"

import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"
import { useTenantStore } from "@/lib/stores/tenantStore"

/**
 * Header dropdown that picks the active tenant ("client") for backend runs.
 *
 * The selected tenant is persisted to localStorage by the store and is included as
 * `tenant_id` in every `POST /api/run` body. Changing the tenant has zero effect on
 * data already in BigQuery — it only routes subsequent runs to a different
 * `~/.mds/tenants.json` entry and changes the `{tenant_id}` token substituted into the
 * manifest's `bronze_pattern`.
 *
 * Renders nothing on the server (the persisted value is only available after hydration)
 * to avoid a hydration mismatch warning.
 */
export default function TenantSelector() {
  const { tenants, selectedTenantId, setSelectedTenantId } = useTenantStore()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) return null
  if (tenants.length === 0) return null

  return (
    <label className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5">
      <span
        className="material-symbols-outlined text-[16px] text-slate-500"
        aria-hidden
      >
        groups
      </span>
      <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        Client
      </span>
      <select
        aria-label="Active client / tenant"
        value={selectedTenantId}
        onChange={(e) => setSelectedTenantId(e.target.value)}
        className={cn(
          "bg-transparent text-sm font-semibold text-slate-800",
          "focus:outline-none focus:ring-1 focus:ring-blue-500 rounded",
        )}
      >
        {tenants.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>
    </label>
  )
}
