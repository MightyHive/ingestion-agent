"use client"

import {useEffect, useState} from "react"
import { useRouter } from "next/navigation"
import { AgentProgressPanel } from "@/components/agents/AgentProgressPanel"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import { generateMockSchema } from "@/lib/mock-agent"

function typeColor(type: string): string {
  if (type.includes("FLOAT") || type === "NUMERIC" || type === "BIGNUMERIC")
    return "bg-amber-50 text-amber-700"
  if (type.includes("INT")) return "bg-purple-50 text-purple-700"
  if (type === "STRING" || type === "BYTES") return "bg-blue-50 text-blue-700"
  if (type === "DATE" || type === "TIMESTAMP") return "bg-green-50 text-green-700"
  if (type === "BOOL") return "bg-slate-100 text-slate-600"
  return "bg-muted text-on-surface-variant"
}

export default function TemplateStep({data, onUpdate}: any) {
  const platform = data.step1?.platform; 
  const columns = data.step2?.columns || [];
  const router   = useRouter()
  const store    = useConnectorStore()
  const {
    schemaProposal,
    isProposing,
    proposalError,
    connectorName,
    selectedFields,
    completedNodes,
  } = store
  const [copied, setCopied] = useState(false)
  const [schema, setSchema] = useState(null)

  useEffect(() => {
    // Solo disparamos la simulación si tenemos los datos y no hay nada en proceso
    if (platform && columns.length > 0 && !schemaProposal && !isProposing) {
      
      const simulateAgent = async () => {
        store.setProposing(true);
        store.setSelectedFields(columns);
        
        // Simulamos el trabajo del arquitecto
        await new Promise(r => setTimeout(r, 1500));
        
        const proposal = generateMockSchema(platform, columns);
        store.setSchemaProposal(proposal);
        store.setProposing(false);
      };
  
      simulateAgent();
    }
  }, [platform, columns.length, schemaProposal, isProposing]); // Se ejecuta si algo de esto cambia

  function handleApprove() {
    // TODO: call backend to approve and continue to scheduler
    router.push("/scheduler")
  }

  function handleReject() {
    router.push("/selectors")
  }

  async function copyDDL() {
    if (!schemaProposal?.ddl) return
    await navigator.clipboard.writeText(schemaProposal.ddl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (!isProposing && !schemaProposal && !proposalError) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <span className="material-symbols-outlined text-4xl text-on-surface-variant">schema</span>
        <p className="text-sm text-on-surface-variant">There is no schema generated.</p>
        <button onClick={() => router.push("/selectors")} className="text-sm font-semibold text-primary hover:underline">
          Go to Selectors
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">Schema</h1>
        <p className="text-sm text-on-surface-variant mt-0.5">
          The Data Architect proposes the following structure for your data.
        </p>
      </div>

      {isProposing && (
        <div className="bg-card rounded-2xl border border-border p-6">
          <AgentProgressPanel completedNodes={completedNodes} active={isProposing} />
          <p className="text-xs text-on-surface-variant mt-4">
            Data Architect is designing the schema. This may take a few seconds.
          </p>
        </div>
      )}

      {/* Error */}
      {proposalError && (
        <div className="bg-card rounded-2xl border border-red-200 p-6 flex items-center gap-3 text-red-700">
          <span className="material-symbols-outlined">error</span>
          <div>
            <p className="font-semibold text-sm">Error while generating the schema</p>
            <p className="text-xs mt-0.5">{proposalError}</p>
          </div>
          <button onClick={() => router.push("/selectors")} className="ml-auto text-xs font-semibold text-primary hover:underline">
            Go to Selectors
          </button>
        </div>
      )}

      {schemaProposal && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">

          <div className="flex flex-col gap-4">
            <div className="bg-card rounded-2xl border border-border p-5 flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-1">
                    Table proposal
                  </p>
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-on-surface-variant text-base">table_chart</span>
                    <code className="text-sm font-mono font-semibold text-primary">
                      {schemaProposal.tableName}
                    </code>
                  </div>
                  <p className="text-xs text-on-surface-variant mt-1">
                    {schemaProposal.columns.length} columns · BigQuery Standard SQL
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium">
                    Standard
                  </span>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider">Field</th>
                      <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider">Type</th>
                      <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider">Mode</th>
                      <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider">Description</th>
                      <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider">Original</th>
                    </tr>
                  </thead>
                  <tbody>
                    {schemaProposal.columns.map((col) => (
                      <tr
                        key={col.original}
                        className="border-b border-border/50 hover:bg-muted/30 transition-colors"
                      >
                        <td className="py-2 px-2">
                          <input
                            type="text"
                            defaultValue={col.name}
                            className="w-full min-w-[120px] text-xs font-mono text-primary bg-background border border-border rounded px-2 py-1"
                            aria-label={`BigQuery column name for ${col.original}`}
                          />
                        </td>
                        <td className="py-2 px-2">
                          <select
                            defaultValue={col.type}
                            className={`text-xs font-semibold px-2 py-1 rounded border border-border bg-background ${typeColor(col.type)}`}
                            aria-label={`Type for ${col.original}`}
                          >
                          </select>
                        </td>
                        <td className="py-2 px-2">
                          <select
                            defaultValue={col.mode}
                            className={`text-xs font-medium border border-border rounded bg-background px-2 py-1 ${
                              col.mode === "REQUIRED" ? "text-on-surface" : "text-on-surface-variant"
                            }`}
                            aria-label={`Mode for ${col.original}`}
                          >
                            <option value="NULLABLE">NULLABLE</option>
                            <option value="REQUIRED">REQUIRED</option>
                          </select>
                        </td>
                        <td className="py-2 px-2 max-w-[220px]">
                          <span className="text-xs text-on-surface-variant line-clamp-3">
                            {col.description?.trim() ? col.description.trim() : "—"}
                          </span>
                        </td>
                        <td className="py-2 px-2">
                          <code className="text-xs font-mono text-on-surface-variant">{col.original}</code>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <details className="bg-card rounded-2xl border border-border overflow-hidden group">
              <summary className="cursor-pointer list-none flex items-center justify-between gap-3 px-5 py-3 border-b border-border bg-muted/30 [&::-webkit-details-marker]:hidden">
                <span className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
                  View SQL DDL Preview
                </span>
                <span className="material-symbols-outlined text-on-surface-variant text-base transition-transform group-open:rotate-180 shrink-0">
                  expand_more
                </span>
              </summary>
              <div className="flex justify-end px-5 pt-3 pb-0">
                <button
                  type="button"
                  onClick={copyDDL}
                  className="flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
                >
                  <span className="material-symbols-outlined text-sm">
                    {copied ? "check" : "content_copy"}
                  </span>
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
              <pre className="p-5 pt-2 text-xs font-mono text-on-surface overflow-x-auto leading-relaxed bg-slate-950 text-slate-100">
                {schemaProposal.ddl}
              </pre>
            </details>
          </div>

          <div className="flex flex-col gap-4">
            <div className="bg-card rounded-2xl border border-border p-5 flex flex-col gap-3">
              <div>
                <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-1">Connector</p>
                <p className="text-sm font-semibold text-on-surface">{connectorName}</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-1">selected fields</p>
                <p className="text-sm font-semibold text-on-surface">{selectedFields.length}</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-1">Table</p>
                <code className="text-xs font-mono text-primary">{schemaProposal.tableName}</code>
              </div>
            </div>

            <div className="bg-card rounded-2xl border border-border p-5">
              <div className="flex items-start gap-2 mb-2">
                <span className="material-symbols-outlined text-primary text-base mt-0.5">smart_toy</span>
                <p className="text-xs font-semibold text-on-surface">Automation Insight</p>
              </div>
              <p className="text-xs text-on-surface-variant leading-relaxed">
                The Data Architect Agent proposes {schemaProposal.columns.filter(c => c.mode === "REQUIRED").length} required fields
                and {schemaProposal.columns.filter(c => c.mode === "NULLABLE").length} as optionals.
                The types were adapted to the BigQuery standard.
              </p>
            </div>

            <div className="flex flex-col gap-2">
              <button
                onClick={handleApprove}
                className="w-full py-2.5 px-4 bg-primary text-white rounded-xl font-semibold text-sm hover:bg-primary/90 transition-colors flex items-center justify-center gap-2"
              >
                <span className="material-symbols-outlined text-base">check_circle</span>
                Approve schema
              </button>
              <button
                onClick={handleReject}
                className="w-full py-2.5 px-4 bg-transparent border border-border text-on-surface-variant rounded-xl font-semibold text-sm hover:bg-muted/50 transition-colors flex items-center justify-center gap-2"
              >
                <span className="material-symbols-outlined text-base">arrow_back</span>
                Go to Selectors
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
