"use client"

import { useEffect, useState } from "react"
import { useCredentialStore } from "@/lib/stores/credentialStore"
import { useTemplateStore, type SavedTemplate } from "@/lib/stores/templateStore"
import { buildExportTableName } from "@/lib/exportTableName"
import SavedTemplatesBrowser from "@/components/data-export/SavedTemplatesBrowser"
import { cn } from "@/lib/utils"

interface ExtractionData {
  templateId: string
  credentialId: string
  tableName: string
}

interface Props {
  data: ExtractionData
  onUpdate: (data: Record<string, unknown>) => void
}

export default function ExtractionStep({ data, onUpdate }: Props) {
  const { credentials } = useCredentialStore()
  const { templates } = useTemplateStore()
  const [connected, setConnected] = useState(false)
  const [connecting, setConnecting] = useState(false)

  const selectedTemplate = templates.find((t) => t.id === data.templateId) ?? null
  const selectedCredential = credentials.find((c) => c.id === data.credentialId) ?? null

  useEffect(() => {
    if (!selectedTemplate || !selectedCredential) return
    const suggested = buildExportTableName(
      selectedCredential.market,
      selectedCredential.brand,
      selectedTemplate.platform,
      selectedTemplate.endpoint
    )
    if (data.tableName !== suggested) {
      onUpdate({ tableName: suggested })
    }
  }, [data.templateId, data.credentialId])

  function handleSelectTemplate(t: SavedTemplate) {
    setConnected(false)
    onUpdate({ templateId: t.id, tableName: "" })
  }

  function handleSelectCredential(id: string) {
    setConnected(false)
    onUpdate({ credentialId: id, tableName: "" })
  }

  async function handleConnect() {
    setConnecting(true)
    await new Promise((r) => setTimeout(r, 1800))
    setConnecting(false)
    setConnected(true)
  }

  return (
    <div className="space-y-8 max-w-[1200px]">
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">Create Extraction</h1>
        <p className="text-sm text-on-surface-variant mt-0.5">
          Choose a template and credentials, then configure the destination table.
        </p>
      </div>

      {/* Template picker */}
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-on-surface uppercase tracking-wider">1 · Template</h2>
        <SavedTemplatesBrowser
          mode="picker"
          selectedId={data.templateId}
          onSelect={handleSelectTemplate}
        />
      </section>

      {/* Credential picker */}
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-on-surface uppercase tracking-wider">2 · Credentials</h2>
        {credentials.length === 0 ? (
          <p className="text-sm text-on-surface-variant">No credentials available. Add one in the Credentials Library.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {credentials.map((cred) => {
              const isSelected = data.credentialId === cred.id
              return (
                <button
                  key={cred.id}
                  type="button"
                  onClick={() => handleSelectCredential(cred.id)}
                  className={cn(
                    "flex items-center gap-4 p-4 rounded-xl border text-left transition-all",
                    isSelected
                      ? "border-primary/40 bg-primary/5"
                      : "border-border bg-card hover:bg-muted/40"
                  )}
                >
                  <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center flex-shrink-0">
                    <span className="material-symbols-outlined text-on-surface-variant text-base">key</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-on-surface">{cred.name}</p>
                    <p className="text-xs text-on-surface-variant">
                      {cred.platform} · {cred.market} · {cred.brand}
                    </p>
                  </div>
                  {cred.status && (
                    <span className={cn(
                      "text-xs font-medium px-2 py-0.5 rounded-full border",
                      cred.status === "Healthy"
                        ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                        : "bg-amber-50 text-amber-700 border-amber-200"
                    )}>
                      {cred.status}
                    </span>
                  )}
                  {isSelected && (
                    <span className="material-symbols-outlined text-primary text-base flex-shrink-0">check_circle</span>
                  )}
                </button>
              )
            })}
          </div>
        )}
      </section>

      {/* Table name + SQL preview */}
      {selectedTemplate && selectedCredential && (
        <section className="flex flex-col gap-4">
          <h2 className="text-sm font-semibold text-on-surface uppercase tracking-wider">3 · Destination table</h2>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
              Table name in BigQuery
            </label>
            <input
              type="text"
              value={data.tableName}
              onChange={(e) => onUpdate({ tableName: e.target.value })}
              className="font-mono text-sm px-3 py-2 border border-border rounded-lg bg-background outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              placeholder="01_region_brand_platform_endpoint"
            />
            <p className="text-xs text-on-surface-variant">Auto-generated from credential + template. You can edit it.</p>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
              SQL Preview (DDL)
            </label>
            <pre className="text-xs font-mono bg-muted rounded-xl p-4 overflow-x-auto text-on-surface-variant whitespace-pre-wrap">
              {selectedTemplate.ddl}
            </pre>
          </div>

          <button
            type="button"
            onClick={handleConnect}
            disabled={connecting || connected || !data.tableName}
            className={cn(
              "self-start px-4 py-2.5 rounded-xl font-semibold text-sm transition-colors flex items-center gap-2",
              connected
                ? "bg-emerald-50 text-emerald-700 border border-emerald-200 cursor-default"
                : "bg-primary text-white hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            <span className="material-symbols-outlined text-base">
              {connected ? "check_circle" : connecting ? "sync" : "cable"}
            </span>
            {connected ? "Connection established" : connecting ? "Connecting…" : "Generate connection"}
          </button>
        </section>
      )}
    </div>
  )
}
