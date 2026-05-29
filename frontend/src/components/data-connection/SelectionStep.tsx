"use client"

import { useCallback, useMemo } from "react"
import { AgentProgressPanel } from "@/components/agents/AgentProgressPanel"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import ColumnSelector from "@/components/connectors/ColumnSelector"
import { getReportEndpoints } from "@/lib/platforms/registry"
import { filterFieldsByReportingLevel } from "@/lib/platforms/field-filter"
import type { PlatformId } from "@/lib/platforms/types"
import { isPlatformId } from "@/lib/platforms/types"
import { useCredentialStore } from "@/lib/stores/credentialStore"

type FieldsStepData = {
  columns: string[]
  reportingLevel: string | null
  credentialIds: string[]
}

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

interface Props {
  data: FieldsStepData
  onUpdate: (d: Partial<FieldsStepData>) => void
}

export default function SelectionStep({ data, onUpdate }: Props) {
  const store = useConnectorStore()
  const { credentials } = useCredentialStore()
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
  const reportingLevel = data.reportingLevel

  const levelLabel = resolveScopeLabel(endpoints, reportingLevel)
  const displayPlatform = platformLabel(connectorId)

  const selectedCredentialNames = data.credentialIds
    .map((id) => credentials.find((c) => c.id === id)?.name)
    .filter(Boolean)
    .join(", ")

  const visibleFields = useMemo(
    () => filterFieldsByReportingLevel(platform, fields, reportingLevel),
    [platform, fields, reportingLevel]
  )

  const KINDS_TABS = useMemo(
    () => [
      { id: "metric", label: "Metrics" },
      { id: "dimension", label: "Dimensions" },
    ],
    []
  )

  const handleSelectionChange = useCallback(
    (ids: string[]) => {
      onUpdate({ columns: ids })
      store.setSelectedFields(ids)
    },
    [onUpdate, store]
  )

  if (!reportingLevel || data.credentialIds.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <span className="material-symbols-outlined text-4xl text-on-surface-variant">tune</span>
        <p className="text-sm text-on-surface-variant">
          Complete credentials and reporting scope in the previous step first.
        </p>
      </div>
    )
  }

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
        <h2 className="text-2xl font-semibold text-on-surface">Select fields &amp; explore data</h2>
        <p className="text-sm text-on-surface-variant mt-0.5">
          Choose fields to extract from {displayPlatform} at the{" "}
          <span className="font-medium text-on-surface">{levelLabel}</span> level.
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

          {!isInvestigating && fields.length > 0 && reportingLevel && (
            <div>
              <p className="text-sm text-on-surface-variant mb-3">
                Only fields valid for <span className="font-medium text-on-surface">{levelLabel}</span> are
                shown.
              </p>
              <ColumnSelector
                key={`${connectorId}-${reportingLevel}`}
                message={`We found ${visibleFields.length} fields valid for ${levelLabel} — select what to include.`}
                columns={visibleFields}
                endpointTabs={KINDS_TABS}
                onSelectionChange={handleSelectionChange}
              />
            </div>
          )}
        </div>

        <div className="flex flex-col gap-4">
          <div className="bg-card rounded-2xl border border-border p-5 space-y-3">
            <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
              Context
            </p>
            <p className="text-sm font-semibold text-on-surface">
              {connectorName ?? "—"} ({displayPlatform})
            </p>
            {selectedCredentialNames && (
              <p className="text-xs text-on-surface">
                Credentials: <span className="font-semibold">{selectedCredentialNames}</span>
              </p>
            )}
            <p className="text-xs text-on-surface">
              Scope: <span className="font-semibold">{levelLabel}</span>
            </p>
            {fields.length > 0 && (
              <p className="text-xs text-on-surface-variant">
                {data.columns.length} of {visibleFields.length} fields selected
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
