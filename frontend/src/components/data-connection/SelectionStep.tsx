"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { AgentProgressPanel } from "@/components/agents/AgentProgressPanel"
import { cn } from "@/lib/utils"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import ColumnSelector from "@/components/connectors/ColumnSelector"
import { getReportEndpoints } from "@/lib/platforms/registry"
import { filterFieldsByReportingLevel } from "@/lib/platforms/field-filter"
import type { PlatformId } from "@/lib/platforms/types"
import { isPlatformId } from "@/lib/platforms/types"

type Step2Data = {
  columns: string[]
  /** Reporting object level (e.g. campaign, ad) — same `id` as in `getReportEndpoints`. */
  reportingLevel: string | null
}

const DEFAULT_STEP2: Step2Data = { columns: [], reportingLevel: null }

function platformLabel(connectorId: string | null): string {
  if (connectorId === "meta") return "Meta Ads"
  if (connectorId === "tiktok") return "TikTok Ads"
  if (connectorId === "youtube") return "YouTube"
  if (connectorId === "google_ads") return "Google Ads"
  if (connectorId === "dv360") return "Display & Video 360"
  return "Unknown platform"
}

function resolveScopeLabel(
  endpoints: readonly { id: string; label: string }[],
  id: string | null
): string {
  if (!id) return "—"
  return endpoints.find((e) => e.id === id)?.label ?? id
}


export default function SelectionStep({ data, onUpdate }: { data: Step2Data; onUpdate: (d: Partial<Step2Data>) => void }) {
  const store = useConnectorStore()
  const d = { ...DEFAULT_STEP2, ...data }
  const {
    connectorId,
    connectorName,
    fields,
    isInvestigating,
    investigationError,
    completedNodes,
  } = store

  const platform = (isPlatformId(connectorId ?? "") ? connectorId : "meta") as PlatformId
  const endpoints = useMemo(() => getReportEndpoints(connectorId ?? "meta"), [connectorId])
  const KINDS_TABS = useMemo(() => [
    { id: "metric", label: "Metrics" },
    { id: "dimension", label: "Dimensions" },
  ], [])


  const [reportingLevel, setReportingLevel] = useState<string | null>(d.reportingLevel)
  useEffect(() => {
    setReportingLevel(d.reportingLevel)
  }, [d.reportingLevel])

  const levelLabel = resolveScopeLabel(endpoints, reportingLevel)
  const displayPlatform = platformLabel(connectorId)

  const visibleFields = useMemo(
    () => filterFieldsByReportingLevel(platform, fields, reportingLevel),
    [platform, fields, reportingLevel]
  )

  const handleSetReportingLevel = useCallback(
    (id: string) => {
      setReportingLevel(id)
      onUpdate({ reportingLevel: id, columns: [] })
      store.setSelectedFields([])
    },
    [onUpdate, store]
  )

  const handleSelectionChange = useCallback(
    (ids: string[]) => {
      onUpdate({ columns: ids, reportingLevel: reportingLevel ?? null })
      store.setSelectedFields(ids)
    },
    [onUpdate, store, reportingLevel]
  )

  if (!connectorName && !isInvestigating) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <span className="material-symbols-outlined text-4xl text-on-surface-variant">hub</span>
        <p className="text-sm text-on-surface-variant">No active connector.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">Field selection</h1>
        <p className="text-sm text-on-surface-variant mt-0.5">
          {connectorName
            ? `Select fields to extract from ${displayPlatform}.`
            : "Investigating the API…"}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-6">
        <div className="bg-card rounded-2xl border border-border p-6">
          {isInvestigating && (
            <AgentProgressPanel completedNodes={completedNodes} active={isInvestigating} />
          )}

          {investigationError && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
              <span className="material-symbols-outlined text-base" aria-hidden>
                error
              </span>
              {investigationError}
            </div>
          )}

          {!isInvestigating && fields.length > 0 && (
            <div className="space-y-5">
              <div>
                <h2 className="text-sm font-semibold text-on-surface">1. Reporting scope</h2>
                <p className="text-sm text-on-surface-variant mt-1.5 max-w-2xl">
                  This sets the grain of each row. You only get fields the API can return
                  for that object level. For example, ad-level or creative details are not
                  available when you only report at campaign.
                </p>
                <div
                  className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 mt-4"
                  role="listbox"
                  aria-label="Reporting level"
                >
                  {endpoints.map((ep) => {
                    const active = reportingLevel === ep.id
                    return (
                      <button
                        key={ep.id}
                        type="button"
                        role="option"
                        aria-selected={active}
                        onClick={() => handleSetReportingLevel(ep.id)}
                        className={cn(
                          "text-left rounded-xl border px-4 py-3 transition-colors",
                          active
                            ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                            : "border-border hover:bg-muted/50"
                        )}
                      >
                        <p className="text-sm font-semibold text-on-surface">{ep.label}</p>
                        <p className="text-xs text-on-surface-variant mt-0.5">
                          One row per {ep.label.toLowerCase()}
                        </p>
                      </button>
                    )
                  })}
                </div>
                {!reportingLevel && (
                  <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mt-3">
                    Select a level above. The field list appears after you pick where you
                    are reporting in the object hierarchy.
                  </p>
                )}
              </div>

              {reportingLevel && (
                <div>
                  <h2 className="text-sm font-semibold text-on-surface mb-1.5">2. Fields for this level</h2>
                  <p className="text-sm text-on-surface-variant mb-3">
                    Only fields that exist at the <span className="font-medium text-on-surface">{levelLabel}</span> level are
                    shown. The tabs help you group metrics (all views) and dimensions (by
                    their object: campaign, ad set, ad, etc.). Anything not in this list for
                    your current scope is not supported here; switch the reporting level to
                    use it.{" "}
                    <span className="text-on-surface font-medium" title="Cross-level rule">
                      Not available at a given level? Change scope above
                    </span>{" "}
                    instead of looking for a disabled field.
                  </p>
                  <ColumnSelector
                    key={`${connectorId}-${reportingLevel}`}
                    message={`We found ${visibleFields.length} fields valid for ${levelLabel} — select what to include in the extraction.`}
                    columns={visibleFields}
                    endpointTabs={KINDS_TABS}
                    onSelectionChange={handleSelectionChange}
                  />
                </div>
              )}
            </div>
          )}
        </div>

        <div className="flex flex-col gap-4">
          <div className="bg-card rounded-2xl border border-border p-5">
            <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-3">
              Active connector
            </p>
            <p className="text-sm font-semibold text-on-surface">
              {connectorName ?? "—"} ({displayPlatform})
            </p>
            {fields.length > 0 && (
              <p className="text-xs text-on-surface-variant mt-1">
                {visibleFields.length} of {fields.length} fields in scope
              </p>
            )}
            {reportingLevel && (
              <p className="text-xs text-on-surface mt-2">
                Scope: <span className="font-semibold">{levelLabel}</span>
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
