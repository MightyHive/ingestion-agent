"use client"

import { useRouter } from "next/navigation"
import { AgentProgressPanel } from "@/components/agents/AgentProgressPanel"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import ColumnSelector from "@/components/connectors/ColumnSelector"
import { generateMockSchema } from "@/lib/mock-agent" 

// 1. Recibimos data y onUpdate del Padre
export default function SelectionStep({ data, onUpdate }: any) {
  const router = useRouter()
  const store  = useConnectorStore()

  // Seguimos usando el store para la investigación de campos (que es un proceso global)
  const { 
    connectorId, 
    connectorName, 
    fields, 
    isInvestigating, 
    investigationError, 
    completedNodes 
  } = store

  /**
   * Ahora handleConfirm es más simple: 
   * Solo le avisa al Padre y al Store local.
   */
  async function handleConfirm(selected: string[]) {
    // Avisamos al Padre (Wizard) para que guarde las columnas en su 'pizarra'
    onUpdate({ columns: selected });
    
    // También actualizamos el store por si otros componentes lo necesitan
    store.setSelectedFields(selected);
    
    // NOTA: Ya no hacemos router.push("/schema") aquí, 
    // porque de eso se encarga el botón "Next" del Padre.
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
              // Aquí pasamos la función que actualiza los datos
              onConfirm={handleConfirm}
              // OPCIONAL: Podrías pasarle 'data.columns' al ColumnSelector 
              // para que ya aparezcan tildadas si el usuario vuelve atrás.
              initialSelected={data?.columns || []} 
            />
          )}
        </div>

        {/* Sidebar de info del conector */}
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