"use client"

import {useEffect, useState} from "react"
import { useRouter } from "next/navigation"
import { AgentProgressPanel } from "@/components/agents/AgentProgressPanel"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import { useTemplateStore } from "@/lib/stores/templateStore"
import { generateMockTemplate } from "@/lib/mock-agent"

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
  const platform       = data.step1?.platform
  const columns        = data.step2?.columns || []
  const reportingLevel = data.step2?.reportingLevel ?? null
  const router         = useRouter()
  const store          = useConnectorStore()
  const { addTemplate } = useTemplateStore()
  const {
    templateProposal,
    isProposing,
    proposalError,
    connectorName,
    selectedFields,
    completedNodes,
  } = store
  const [copied, setCopied] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    // Solo disparamos la simulación si tenemos los datos y no hay nada en proceso
    if (platform && columns.length > 0 && !templateProposal && !isProposing) {
      
      const simulateAgent = async () => {
        store.setProposing(true);
        store.setSelectedFields(columns);
        
        // Simulamos el trabajo del arquitecto
        await new Promise(r => setTimeout(r, 1500));
        
        const proposal = generateMockTemplate(platform, columns, reportingLevel);
        store.setTemplateProposal(proposal);
        store.setProposing(false);
      };
  
      simulateAgent();
    }
  }, [platform, columns.length, templateProposal, isProposing]); // Se ejecuta si algo de esto cambia

  function handleApprove() {
    if (templateProposal) {
      addTemplate({
        tableName: templateProposal.tableName,
        platform:  platform ?? "",
        endpoint:  reportingLevel ?? "all",
        columns:   templateProposal.columns,
        ddl:       templateProposal.ddl,
      })
    }
    setSaved(true)
  }

  async function copyDDL() {
    if (!templateProposal?.ddl) return
    await navigator.clipboard.writeText(templateProposal.ddl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (!isProposing && !templateProposal && !proposalError) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <span className="material-symbols-outlined text-4xl text-on-surface-variant">template</span>
        <p className="text-sm text-on-surface-variant">There is no template generated.</p>
        <button onClick={() => router.push("/selectors")} className="text-sm font-semibold text-primary hover:underline">
          Go to Selectors
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">Template</h1>
        <p className="text-sm text-on-surface-variant mt-0.5">
          The Data Architect proposes the following structure for your data.
        </p>
      </div>

      {isProposing && (
        <div className="bg-card rounded-2xl border border-border p-6">
          <AgentProgressPanel completedNodes={completedNodes} active={isProposing} />
          <p className="text-xs text-on-surface-variant mt-4">
            Data Architect is designing the template. This may take a few seconds.
          </p>
        </div>
      )}

      {/* Error */}
      {proposalError && (
        <div className="bg-card rounded-2xl border border-red-200 p-6 flex items-center gap-3 text-red-700">
          <span className="material-symbols-outlined">error</span>
          <div>
            <p className="font-semibold text-sm">Error while generating the template</p>
            <p className="text-xs mt-0.5">{proposalError}</p>
          </div>
          <button onClick={() => router.push("/selectors")} className="ml-auto text-xs font-semibold text-primary hover:underline">
            Go to Selectors
          </button>
        </div>
      )}

      {templateProposal && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">

          <div className="flex flex-col gap-4">
            <div className="bg-card rounded-2xl border border-border p-5 flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-1">
                    Template proposal
                  </p>
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-on-surface-variant text-base">table_chart</span>
                    <code className="text-sm font-mono font-semibold text-primary">
                      {templateProposal.tableName}
                    </code>
                  </div>
                  <p className="text-xs text-on-surface-variant mt-1">
                    {templateProposal.columns.length} columns · BigQuery Standard SQL
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs px-2 py-0.5 rounded-full bg-ermerald-50 text-emerald-700 border border-emerald-200 font-medium">
                    Standard
                  </span>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider w-24">Field</th>
                      <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider w-24">Type</th>
                      <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider w-24">Mode</th>
                      <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider w-48">Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {templateProposal.columns.map((col) => (
                      <tr
                        key={col.original}
                        className="border-b border-border/50 hover:bg-muted/30 transition-colors"
                      >
                        <td className="py-2 px-2 w-48">
                          <code className="text-xs font-mono text-on-surface-variant">{col.name}</code>
                        </td>
                        <td className="py-2 px-2 w-24">
                          <code className="text-xs font-mono text-on-surface-variant">{col.type}</code>
                        </td>
                        <td className="py-2 px-2 w-24">
                          <code className="text-xs font-mono text-on-surface-variant">{col.mode}</code>
                        </td>
                        <td className="py-2 px-2">
                          <span className="text-xs text-on-surface-variant">
                            {col.description?.trim() ? col.description.trim() : "—"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            
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
                <code className="text-xs font-mono text-primary">{templateProposal.tableName}</code>
              </div>
            </div>

            <div className="bg-card rounded-2xl border border-border p-5">
              <div className="flex items-start gap-2 mb-2">
                <span className="material-symbols-outlined text-primary text-base mt-0.5">smart_toy</span>
                <p className="text-xs font-semibold text-on-surface">Automation Insight</p>
              </div>
              <p className="text-xs text-on-surface-variant leading-relaxed">
                The Data Architect Agent proposes {templateProposal.columns.filter(c => c.mode === "REQUIRED").length} required fields
                and {templateProposal.columns.filter(c => c.mode === "NULLABLE").length} as optionals.
                The types were adapted to the BigQuery standard.
              </p>
            </div>

            {saved ? (
              <div className="flex flex-col gap-2">
                <div className="w-full py-3 px-4 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center gap-2 text-emerald-800 text-sm font-semibold">
                  <span className="material-symbols-outlined text-base">check_circle</span>
                  Template saved
                </div>
                <p className="text-xs text-on-surface-variant text-center">
                  <code className="font-mono">{templateProposal.tableName}</code> is ready to use.
                </p>
                <button
                  onClick={() => router.push("/data-export")}
                  className="w-full py-2.5 px-4 bg-primary text-white rounded-xl font-semibold text-sm hover:bg-primary/90 transition-colors flex items-center justify-center gap-2"
                >
                  <span className="material-symbols-outlined text-base">upload</span>
                  Go to Data Export
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                <button
                  onClick={handleApprove}
                  className="w-full py-2.5 px-4 bg-primary text-white rounded-xl font-semibold text-sm hover:bg-primary/90 transition-colors flex items-center justify-center gap-2"
                >
                  <span className="material-symbols-outlined text-base">save</span>
                  Save template
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
