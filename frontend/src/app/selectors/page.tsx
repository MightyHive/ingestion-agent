"use client"

import { useRouter } from "next/navigation"
import { AgentProgressPanel } from "@/components/agents/AgentProgressPanel"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import ColumnSelector from "@/components/connectors/ColumnSelector"

export default function SelectorsPage() {
  const router = useRouter()
  const store  = useConnectorStore()

  const { connectorName, fields, isInvestigating, investigationError, completedNodes, sessionId } =
    store

  function handleConfirm(selected: string[]) {
    store.setSelectedFields(selected)
    store.setProposing(true)
    void store.submitUserInput(sessionId!, { columns_selected: selected })
    router.push("/schema")
  }

  if (!connectorName && !isInvestigating) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <span className="material-symbols-outlined text-4xl text-on-surface-variant">hub</span>
        <p className="text-sm text-on-surface-variant">No active connector.</p>
        <button onClick={() => router.push("/connectors")} className="text-sm font-semibold text-primary hover:underline">
          Go to Connectors
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">Selectors</h1>
        <p className="text-sm text-on-surface-variant mt-0.5">
          {connectorName
            ? `Available fields for ${connectorName}. Choose the columns you need for extraction.`
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
              <span className="material-symbols-outlined text-base">error</span>
              {investigationError}
            </div>
          )}
          {!isInvestigating && fields.length > 0 && (
            <ColumnSelector
              message={`API investigation complete. ${fields.length} fields are available — select those to extract.`}
              columns={fields}
              onConfirm={handleConfirm}
            />
          )}
        </div>

        <div className="flex flex-col gap-4">
          <div className="bg-card rounded-2xl border border-border p-5">
            <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-3">Active connector</p>
            <p className="text-sm font-semibold text-on-surface">{connectorName ?? "—"}</p>
            {fields.length > 0 && (
              <p className="text-xs text-on-surface-variant mt-1">{fields.length} fields available</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
