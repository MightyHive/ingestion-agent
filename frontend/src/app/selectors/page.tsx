"use client"

import { useRouter } from "next/navigation"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import ColumnSelector from "@/components/connectors/ColumnSelector"

const NODE_LABELS: Record<string, string> = {
  coordinator:    "Coordinating Agent",
  api_researcher: "API Researcher",
  data_architect: "Data Architect",
}

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
        <p className="text-sm text-on-surface-variant">No hay ningún conector activo.</p>
        <button onClick={() => router.push("/connectors")} className="text-sm font-semibold text-primary hover:underline">
          Ir a Connectors
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">Selectors</h1>
        <p className="text-sm text-on-surface-variant mt-0.5">
          {connectorName ? `Available fields of ${connectorName}. Choose the ones you need for extraction.` : "Investigating the API.."}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-6">
        <div className="bg-card rounded-2xl border border-border p-6">
          {isInvestigating && (
            <div className="flex flex-col gap-3">
              <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-2">Agent progress</p>
              {completedNodes.map((node) => (
                <div key={node} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-200">
                  <span className="material-symbols-outlined text-emerald-600 text-base">check_circle</span>
                  <span className="text-sm font-medium text-emerald-800">{NODE_LABELS[node] ?? node}</span>
                </div>
              ))}
              <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-blue-50 border border-blue-200">
                <span className="material-symbols-outlined text-blue-600 text-base animate-spin">sync</span>
                <span className="text-sm font-medium text-blue-800">Investigando la API...</span>
              </div>
            </div>
          )}
          {investigationError && (
            <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
              <span className="material-symbols-outlined text-base">error</span>
              {investigationError}
            </div>
          )}
          {!isInvestigating && fields.length > 0 && (
            <ColumnSelector
              message={`Investigué la API. Encontré ${fields.length} campos disponibles. Seleccioná los que querés extraer.`}
              columns={fields}
              onConfirm={handleConfirm}
            />
          )}
        </div>

        <div className="flex flex-col gap-4">
          <div className="bg-card rounded-2xl border border-border p-5">
            <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-3">Conector activo</p>
            <p className="text-sm font-semibold text-on-surface">{connectorName ?? "—"}</p>
            {fields.length > 0 && <p className="text-xs text-on-surface-variant mt-1">{fields.length} campos disponibles</p>}
          </div>
          <div className="bg-card rounded-2xl border border-border p-5">
            <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-2">Session</p>
            <p className="text-xs font-mono text-on-surface-variant break-all">{sessionId ?? "—"}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
