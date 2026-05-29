"use client"

import { useCallback, useMemo } from "react"
import { AgentProgressPanel } from "@/components/agents/AgentProgressPanel"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import ColumnSelector from "@/components/connectors/ColumnSelector"
import ExplorationPreviewPanel from "@/components/data-connection/ExplorationPreviewPanel"
import { getReportEndpoints } from "@/lib/platforms/registry"
import { filterFieldsByReportingLevel } from "@/lib/platforms/field-filter"
import type { PlatformId } from "@/lib/platforms/types"
import { isPlatformId } from "@/lib/platforms/types"
import { cn } from "@/lib/utils"

export type ScopeFieldsData = {
  reportingLevel: string | null
  columns: string[]
}

function resolveScopeLabel(
  endpoints: readonly { id: string; label: string }[],
  id: string | null
): string {
  if (!id) return "—"
  return endpoints.find((e) => e.id === id)?.label ?? id
}

interface Props {
  data: ScopeFieldsData
  onUpdate: (d: Partial<ScopeFieldsData>) => void
}

export default function ScopeFieldsStep({ data, onUpdate }: Props) {
  const store = useConnectorStore()
  const {
    connectorId,
    fields,
    isInvestigating,
    investigationError,
    completedNodes,
  } = store

  const platform = (isPlatformId(connectorId ?? "") ? connectorId : "meta") as PlatformId
  const endpoints = useMemo(() => getReportEndpoints(connectorId ?? "meta"), [connectorId])
  const levelLabel = resolveScopeLabel(endpoints, data.reportingLevel)

  const visibleFields = useMemo(
    () => filterFieldsByReportingLevel(platform, fields, data.reportingLevel),
    [platform, fields, data.reportingLevel]
  )

  const KINDS_TABS = useMemo(
    () => [
      { id: "metric", label: "Metrics" },
      { id: "dimension", label: "Dimensions" },
    ],
    []
  )

  const handleSetReportingLevel = useCallback(
    (id: string) => {
      onUpdate({ reportingLevel: id, columns: [] })
      store.setSelectedFields([])
    },
    [onUpdate, store]
  )

  const handleSelectionChange = useCallback(
    (ids: string[]) => {
      onUpdate({ columns: ids })
      store.setSelectedFields(ids)
    },
    [onUpdate, store]
  )

  if (!connectorId) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <span className="material-symbols-outlined text-4xl text-on-surface-variant">hub</span>
        <p className="text-sm text-on-surface-variant">Select a connector first.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div>
        <h2 className="text-2xl font-semibold text-on-surface">Scope &amp; Fields</h2>
        <p className="text-sm text-on-surface-variant mt-0.5">
          Choose the reporting level and select the fields to include in your extraction.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(360px,420px)] gap-6 items-start">
        <div className="space-y-6">
          <section className="bg-card rounded-2xl border border-border p-6 space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-on-surface">1. Reporting scope</h3>
              <p className="text-sm text-on-surface-variant mt-1">
                Sets the grain of each row in your extract.
              </p>
            </div>

            <div
              className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2"
              role="listbox"
              aria-label="Reporting level"
            >
              {endpoints.map((ep) => {
                const active = data.reportingLevel === ep.id
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

            {!data.reportingLevel && (
              <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                Select a reporting level to continue.
              </p>
            )}
          </section>

          <section className="bg-card rounded-2xl border border-border p-6">
            <div className="mb-4">
              <h3 className="text-sm font-semibold text-on-surface">2. Select fields</h3>
              <p className="text-sm text-on-surface-variant mt-1">
                Choose dimensions and metrics to include in your extraction.
              </p>
            </div>

            {!data.reportingLevel ? (
              <p className="text-sm text-on-surface-variant py-6 text-center">
                Choose a reporting scope above to see available fields.
              </p>
            ) : isInvestigating ? (
              <AgentProgressPanel completedNodes={completedNodes} active={isInvestigating} />
            ) : investigationError ? (
              <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
                <span className="material-symbols-outlined text-base" aria-hidden>
                  error
                </span>
                {investigationError}
              </div>
            ) : fields.length > 0 ? (
              <div>
                <p className="text-sm text-on-surface-variant mb-3">
                  Only fields valid for{" "}
                  <span className="font-medium text-on-surface">{levelLabel}</span> are shown.
                </p>
                <ColumnSelector
                  key={`${connectorId}-${data.reportingLevel}`}
                  message={`We found ${visibleFields.length} fields valid for ${levelLabel} — select what to include.`}
                  columns={visibleFields}
                  endpointTabs={KINDS_TABS}
                  onSelectionChange={handleSelectionChange}
                />
              </div>
            ) : (
              <p className="text-sm text-on-surface-variant py-6 text-center">
                No fields available yet. The agent is still loading field metadata.
              </p>
            )}
          </section>
        </div>

        <ExplorationPreviewPanel
          reportingLevel={data.reportingLevel}
          selectedColumns={data.columns}
        />
      </div>
    </div>
  )
}
