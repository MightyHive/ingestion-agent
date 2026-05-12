"use client"

import { useEffect, useRef, useState } from "react"
import { useCredentialStore } from "@/lib/stores/credentialStore"
import { useTemplateStore } from "@/lib/stores/templateStore"
import { buildExportTableName } from "@/lib/exportTableName"
import { buildBigQueryCreateDdl } from "@/lib/bigquery-ddl"
import { cn } from "@/lib/utils"

function buildGcsObjectUri(bucket: string, prefix: string, objectKey: string): string {
  const b = bucket.replace(/^gs:\/\//i, "").trim().replace(/\/+$/, "")
  const pref = prefix.trim().replace(/^\/+|\/+$/g, "")
  const key = objectKey.trim()
  if (!b || !key) return ""
  return pref ? `gs://${b}/${pref}/${key}` : `gs://${b}/${key}`
}

interface ExtractionData {
  platform: string
  templateId: string
  credentialIds: string[]
  tableNames: Record<string, string>
}

interface Props {
  data: ExtractionData
  onUpdate: (data: Record<string, unknown>) => void
  projectId: string
  destinationKind: "bigquery" | "gcs"
  bigQueryDataset: string
  gcsBucket: string
  gcsPrefix: string
}

export default function ExtractionStep({
  data,
  onUpdate,
  projectId,
  destinationKind,
  bigQueryDataset,
  gcsBucket,
  gcsPrefix,
}: Props) {
  const { credentials } = useCredentialStore()
  const { templates } = useTemplateStore()
  const [connected, setConnected] = useState(false)
  const [connecting, setConnecting] = useState(false)
  const ALL_PLATFORMS = "__all__"

  const normalizePlatform = (platform: string) =>
    platform.trim().toLowerCase().replace(/\s+/g, "_")

  const selectedTemplate = templates.find((t) => t.id === data.templateId) ?? null
  const activePlatform = selectedTemplate?.platform ?? ""
  const selectedCredentials = data.credentialIds
    .map((id) => credentials.find((c) => c.id === id))
    .filter((cred): cred is (typeof credentials)[number] => Boolean(cred))
  const lastAutoSeedRef = useRef("")

  const availablePlatforms = Array.from(new Set(templates.map((t) => t.platform))).sort()
  const filteredTemplates = data.platform
    ? templates.filter((t) => normalizePlatform(t.platform) === normalizePlatform(data.platform))
    : templates
  const compatibleCredentials = activePlatform
    ? credentials.filter((c) => normalizePlatform(c.platform) === normalizePlatform(activePlatform))
    : []

  useEffect(() => {
    if (!data.platform || !selectedTemplate) return
    if (normalizePlatform(selectedTemplate.platform) === normalizePlatform(data.platform)) return
    onUpdate({ templateId: "", credentialIds: [], tableNames: {} })
  }, [data.platform, onUpdate, selectedTemplate])

  useEffect(() => {
    if (!activePlatform || data.credentialIds.length === 0) return
    const validCredentialIds = data.credentialIds.filter((id) => {
      const credential = credentials.find((c) => c.id === id)
      return credential && normalizePlatform(credential.platform) === normalizePlatform(activePlatform)
    })
    if (validCredentialIds.length !== data.credentialIds.length) {
      const nextTableNames = Object.fromEntries(
        Object.entries(data.tableNames).filter(([id]) => validCredentialIds.includes(id))
      )
      onUpdate({ credentialIds: validCredentialIds, tableNames: nextTableNames })
    }
  }, [activePlatform, credentials, data.credentialIds, data.tableNames, onUpdate])

  useEffect(() => {
    if (!selectedTemplate || selectedCredentials.length === 0) return
    const selectionKey = `${selectedTemplate.id}|${selectedCredentials.map((c) => c.id).join(",")}`
    if (lastAutoSeedRef.current === selectionKey && selectedCredentials.every((c) => data.tableNames[c.id]?.trim())) {
      return
    }
    const nextTableNames: Record<string, string> = {}
    selectedCredentials.forEach((cred) => {
      const existing = data.tableNames[cred.id]?.trim()
      nextTableNames[cred.id] =
        existing ||
        buildExportTableName(
          cred.market,
          cred.brand,
          selectedTemplate.platform,
          selectedTemplate.endpoint
        )
    })
    const currentKeys = Object.keys(data.tableNames).sort().join("|")
    const nextKeys = Object.keys(nextTableNames).sort().join("|")
    const isSame =
      currentKeys === nextKeys &&
      Object.keys(nextTableNames).every((id) => nextTableNames[id] === data.tableNames[id])
    if (isSame) return
    lastAutoSeedRef.current = selectionKey
    onUpdate({ tableNames: nextTableNames })
  }, [data.tableNames, onUpdate, selectedCredentials, selectedTemplate])

  const hasAllTableNames =
    selectedCredentials.length > 0 &&
    selectedCredentials.every((cred) => (data.tableNames[cred.id] ?? "").trim() !== "")

  function handleSelectPlatform(platform: string) {
    setConnected(false)
    if (platform === ALL_PLATFORMS) {
      onUpdate({ platform: "" })
      return
    }
    onUpdate({ platform, templateId: "", credentialIds: [], tableNames: {} })
  }

  function handleSelectTemplate(templateId: string) {
    setConnected(false)
    onUpdate({ templateId, credentialIds: [], tableNames: {} })
  }

  function handleToggleCredential(id: string) {
    setConnected(false)
    const exists = data.credentialIds.includes(id)
    const credentialIds = exists ? data.credentialIds.filter((c) => c !== id) : [...data.credentialIds, id]
    const tableNames = Object.fromEntries(
      Object.entries(data.tableNames).filter(([credentialId]) => credentialIds.includes(credentialId))
    )
    onUpdate({ credentialIds, tableNames })
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
          Choose platform, template, and compatible credentials, then configure the destination table.
        </p>
      </div>

      {/* Platform picker */}
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-on-surface uppercase tracking-wider">1 · Platform</h2>
        {availablePlatforms.length === 0 ? (
          <p className="text-sm text-on-surface-variant">No templates available yet. Add one in Data Connection.</p>
        ) : (
          <div className="flex gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => handleSelectPlatform(ALL_PLATFORMS)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors",
                data.platform === ""
                  ? "bg-primary text-white border-primary"
                  : "bg-card text-on-surface border-border hover:border-primary/40"
              )}
            >
              All
            </button>
            {availablePlatforms.map((platform) => {
              const isSelected = normalizePlatform(data.platform) === normalizePlatform(platform)
              return (
                <button
                  key={platform}
                  type="button"
                  onClick={() => handleSelectPlatform(platform)}
                  className={cn(
                    "px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors",
                    isSelected
                      ? "bg-primary text-white border-primary"
                      : "bg-card text-on-surface border-border hover:border-primary/40"
                  )}
                >
                  {platform}
                </button>
              )
            })}
          </div>
        )}
      </section>

      {/* Template picker */}
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-on-surface uppercase tracking-wider">2 · Template</h2>
        {filteredTemplates.length === 0 ? (
          <p className="text-sm text-on-surface-variant">No templates available for this platform.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {filteredTemplates.map((template) => {
              const isSelected = data.templateId === template.id
              return (
                <button
                  key={template.id}
                  type="button"
                  onClick={() => handleSelectTemplate(template.id)}
                  className={cn(
                    "flex items-center gap-4 p-4 rounded-xl border text-left transition-all",
                    isSelected
                      ? "border-primary/40 bg-primary/5"
                      : "border-border bg-card hover:bg-muted/40"
                  )}
                >
                  <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center flex-shrink-0">
                    <span className="material-symbols-outlined text-on-surface-variant text-base">table_chart</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-on-surface font-mono">{template.tableName}</p>
                    <p className="text-xs text-on-surface-variant">
                      {template.platform} · {template.endpoint}
                    </p>
                  </div>
                  {isSelected && (
                    <span className="material-symbols-outlined text-primary text-base flex-shrink-0">check_circle</span>
                  )}
                </button>
              )
            })}
          </div>
        )}
      </section>

      {/* Credential picker */}
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-on-surface uppercase tracking-wider">3 · Credentials</h2>
        {!activePlatform ? (
          <p className="text-sm text-on-surface-variant">Select a platform and template first.</p>
        ) : compatibleCredentials.length === 0 ? (
          <p className="text-sm text-on-surface-variant">
            No compatible credentials for <strong>{activePlatform}</strong>. Add one in Credentials Library.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {compatibleCredentials.map((cred) => {
              const isSelected = data.credentialIds.includes(cred.id)
              return (
                <button
                  key={cred.id}
                  type="button"
                  onClick={() => handleToggleCredential(cred.id)}
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
      {selectedTemplate && selectedCredentials.length > 0 && (
        <section className="flex flex-col gap-4">
          <h2 className="text-sm font-semibold text-on-surface uppercase tracking-wider">4 · Destination tables</h2>

          <div className="flex flex-col gap-3">
            {selectedCredentials.map((cred) => (
              <div key={cred.id} className="flex flex-col gap-1.5">
                <label className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
                  {cred.name} ({cred.market} · {cred.brand})
                </label>
                <input
                  type="text"
                  value={data.tableNames[cred.id] ?? ""}
                  onChange={(e) =>
                    onUpdate({
                      tableNames: {
                        ...data.tableNames,
                        [cred.id]: e.target.value,
                      },
                    })}
                  className="font-mono text-sm px-3 py-2 border border-border rounded-lg bg-background outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                  placeholder="01_bronze_brand_market_platform_endpoint"
                />
              </div>
            ))}
            <p className="text-xs text-on-surface-variant">
              One destination table per selected credential. Auto-generated and fully editable.
            </p>
          </div>

          <button
            type="button"
            onClick={handleConnect}
            disabled={connecting || connected || !hasAllTableNames}
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

          <details className="group rounded-2xl border border-border bg-card open:pb-1">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 text-sm font-semibold text-on-surface [&::-webkit-details-marker]:hidden">
              <span>
                {destinationKind === "bigquery"
                  ? "SQL preview (DDL)"
                  : "Destination preview (GCS)"}
              </span>
              <span className="material-symbols-outlined text-on-surface-variant transition-transform group-open:rotate-180">
                expand_more
              </span>
            </summary>
            <div className="border-t border-border px-5 pb-5 pt-4 flex flex-col gap-4">
              {destinationKind === "bigquery"
                ? selectedCredentials.map((cred) => {
                    const ddl = buildBigQueryCreateDdl(
                      data.tableNames[cred.id] ?? "",
                      selectedTemplate.columns,
                      {
                        projectId: projectId || "project",
                        dataset: bigQueryDataset.trim() || "dataset",
                      }
                    )
                    return (
                      <div
                        key={`ddl-${cred.id}`}
                        className="bg-card rounded-2xl border border-border p-5 flex flex-col gap-3"
                      >
                        <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
                          {cred.name} ({cred.market} · {cred.brand})
                        </p>
                        <p className="text-xs text-on-surface-variant">
                          {selectedTemplate.columns.length} columns · BigQuery Standard SQL
                        </p>
                        <pre className="text-xs font-mono text-on-surface-variant whitespace-pre-wrap overflow-x-auto leading-relaxed">
                          {ddl}
                        </pre>
                      </div>
                    )
                  })
                : selectedCredentials.map((cred) => {
                    const uri = buildGcsObjectUri(
                      gcsBucket,
                      gcsPrefix,
                      data.tableNames[cred.id] ?? ""
                    )
                    return (
                      <div
                        key={`gcs-${cred.id}`}
                        className="bg-card rounded-2xl border border-border p-5 flex flex-col gap-2"
                      >
                        <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
                          {cred.name} ({cred.market} · {cred.brand})
                        </p>
                        <p className="text-xs text-on-surface-variant">
                          Object key matches the table name above. Adjust bucket or prefix in step 1 if needed.
                        </p>
                        {uri ? (
                          <code className="text-xs font-mono text-primary break-all">{uri}</code>
                        ) : (
                          <span className="text-xs text-on-surface-variant">
                            Set bucket and table name to see a full <code className="font-mono">gs://</code> path.
                          </span>
                        )}
                      </div>
                    )
                  })}
            </div>
          </details>
        </section>
      )}
    </div>
  )
}
