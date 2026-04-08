"use client"

import { useRouter } from "next/navigation"
import { AgentProgressPanel } from "@/components/agents/AgentProgressPanel"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import ColumnSelector from "@/components/connectors/ColumnSelector"
import { generateMockSchema } from "@/lib/mock-agent" 

const IS_MOCK = process.env.NEXT_PUBLIC_MOCK === "true"
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export default function SelectorsPage() {
  const router = useRouter()
  const store  = useConnectorStore()

  const { 
    connectorId, 
    connectorName, 
    fields, 
    isInvestigating, 
    investigationError, 
    completedNodes, 
    sessionId 
  } = store

  /**
   * Lógica de Confirmación con Reintentos (Retry Logic)
   * Se encarga de enviar la selección al backend y manejar el flujo hacia /schema.
   */
  async function handleConfirm(selected: string[]) {
    const MAX_RETRIES = 3;
    const RETRY_DELAY = 2000; // 2 segundos

    const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

    // Inicializamos estados y navegamos para dar feedback inmediato
    store.setSelectedFields(selected)
    store.setProposalError(null)
    store.setProposing(true)
    router.push("/schema")

    for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
      try {
        if (IS_MOCK) {
          // Simulación de delay y generación local de esquema
          await new Promise(r => setTimeout(r, 1800))
          const proposal = generateMockSchema(connectorId ?? "meta", selected)
          store.setSchemaProposal(proposal)
        } else {
          const response = await fetch(`${API_BASE}/api/submit_input`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ 
              session_id: sessionId, 
              user_input: { columns_selected: selected } 
            }),
          })

          if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`)

          const reader = response.body.getReader()
          const decoder = new TextDecoder()
          let buffer = ""

          // Procesamiento manual del stream SSE
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            
            buffer += decoder.decode(value, { stream: true })
            const chunks = buffer.split("\n\n")
            buffer = chunks.pop() ?? ""

            for (const chunk of chunks) {
              const line = chunk.replace(/^data:\s*/, "").trim()
              if (!line) continue
              try {
                const event = JSON.parse(line)
                // Si recibimos el evento final con la estructura del backend de main:
                if (event.type === "final" && event.ui_trigger?.data?.ddl) {
                  const data = event.ui_trigger.data
                  store.setSchemaProposal({
                    tableName: data.tableName || "Pending Schema",
                    columns: data.columns || [],
                    ddl: data.ddl
                  })
                }
              } catch { /* Ignorar errores de parseo parcial del chunk */ }
            }
          }
        }

        // Si llegamos aquí sin errores, el flujo terminó con éxito
        return; 

      } catch (err) {
        console.warn(`Intento ${attempt} fallido:`, err)
        
        // Si es el último intento, disparamos el error visual al store
        if (attempt === MAX_RETRIES) {
          store.setProposalError(
            err instanceof Error ? err.message : "Error persistent after retries"
          )
          store.setProposing(false)
        } else {
          // Espera incremental antes del próximo intento
          await sleep(RETRY_DELAY * attempt)
        }
      }
    }
  }

  // --- Renderizado (Se mantiene el estilo MD3 de main) ---

  if (!connectorName && !isInvestigating) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <span className="material-symbols-outlined text-4xl text-on-surface-variant">hub</span>
        <p className="text-sm text-on-surface-variant">No active connector.</p>
        <button 
          onClick={() => router.push("/connectors")} 
          className="text-sm font-semibold text-primary hover:underline"
        >
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