"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { useShallow } from "zustand/react/shallow"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import type { RunResult } from "@/lib/stores/connectorStore"
import { useTemplateStore } from "@/lib/stores/templateStore"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"

function previewColumnOrder(result: RunResult | null): string[] {
  if (!result) return []
  if (result.columns.length > 0) return result.columns
  const row = result.rows_preview[0]
  if (row && typeof row === "object") return Object.keys(row)
  return []
}

function cellPreview(value: unknown): string {
  if (value === null || value === undefined) return "—"
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

export default function TemplateStep({
  data,
  onUpdate: _onUpdate,
}: {
  data: {
    step1?: { platform?: string }
    step2?: { columns?: string[]; reportingLevel?: string | null }
  }
  onUpdate?: (d: Record<string, unknown>) => void
}) {
  void _onUpdate
  const platform = data.step1?.platform
  const columns = data.step2?.columns ?? []
  const reportingLevel = data.step2?.reportingLevel ?? null
  const router = useRouter()
  const {
    connectorId,
    templateProposal,
    isProposing,
    isRunning,
    proposalError,
    runError,
    runRequestId,
    runResult,
    connectorName,
    clearRunAndProposalErrors,
    setSelectedFields,
    runPipeline,
  } = useConnectorStore(
    useShallow((s) => ({
      connectorId: s.connectorId,
      templateProposal: s.templateProposal,
      isProposing: s.isProposing,
      isRunning: s.isRunning,
      proposalError: s.proposalError,
      runError: s.runError,
      runRequestId: s.runRequestId,
      runResult: s.runResult,
      connectorName: s.connectorName,
      clearRunAndProposalErrors: s.clearRunAndProposalErrors,
      setSelectedFields: s.setSelectedFields,
      runPipeline: s.runPipeline,
    }))
  )
  const { addTemplate } = useTemplateStore()

  const [copied, setCopied] = useState(false)
  const [saved, setSaved] = useState(false)
  const [templateName, setTemplateName] = useState("")

  const columnsKey = useMemo(() => [...columns].sort().join("|"), [columns])
  const loading = isProposing || isRunning
  const pipelineError = runError ?? proposalError

  useEffect(() => {
    if (templateProposal?.tableName) {
      setTemplateName(templateProposal.tableName)
    }
  }, [templateProposal?.tableName])

  useEffect(() => {
    if (columns.length === 0) return
    const s = useConnectorStore.getState()
    if (!s.connectorId) return
    if (s.templateProposal || s.isRunning || s.isProposing) return
    if (s.runError || s.proposalError) return
    s.setSelectedFields(columns)
    void s.runPipeline()
  }, [columnsKey, connectorId])

  const handleRetry = useCallback(() => {
    clearRunAndProposalErrors()
    setSelectedFields(columns)
    void runPipeline()
  }, [clearRunAndProposalErrors, setSelectedFields, runPipeline, columns])

  const handleApprove = useCallback(() => {
    if (!templateProposal) return
    const name = templateName.trim() || templateProposal.tableName
    addTemplate({
      tableName: name,
      platform: platform ?? "",
      endpoint: reportingLevel ?? "all",
      columns: templateProposal.columns,
      ddl: templateProposal.ddl,
    })
    setSaved(true)
  }, [addTemplate, platform, templateName, templateProposal, reportingLevel])

  async function copyDDL() {
    if (!templateProposal?.ddl) return
    await navigator.clipboard.writeText(templateProposal.ddl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const previewCols = previewColumnOrder(runResult)
  const previewRows = runResult?.rows_preview ?? []

  if (!loading && !templateProposal && !pipelineError && columns.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <span className="material-symbols-outlined text-4xl text-on-surface-variant">template</span>
        <p className="text-sm text-on-surface-variant">There is no template generated.</p>
        <p className="text-xs text-on-surface-variant">Select at least one field in the previous step.</p>
        <button
          type="button"
          onClick={() => router.push("/data-connection")}
          className="text-sm font-semibold text-primary hover:underline"
        >
          Back to data connection
        </button>
      </div>
    )
  }

  if (!loading && !templateProposal && !pipelineError && columns.length > 0 && !connectorId) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <span className="material-symbols-outlined text-4xl text-on-surface-variant">link_off</span>
        <p className="text-sm text-on-surface-variant">No connector is active. Go back and choose a connector.</p>
        <button
          type="button"
          onClick={() => router.push("/data-connection")}
          className="text-sm font-semibold text-primary hover:underline"
        >
          Back to data connection
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">Template</h1>
        <p className="text-sm text-on-surface-variant mt-0.5">
          Review the proposed warehouse table, DDL from the ingestion run, and a sample of rows.
        </p>
      </div>

      {pipelineError && (
        <div className="bg-card rounded-2xl border border-red-200 p-6 flex flex-col gap-3 text-red-700">
          <div className="flex items-start gap-3">
            <span className="material-symbols-outlined shrink-0">error</span>
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-sm">Run failed</p>
              <p className="text-xs mt-1 break-words">{pipelineError}</p>
              {runRequestId ? (
                <p className="text-xs mt-2 font-mono text-red-800/90">
                  Request-ID: <span className="select-all">{runRequestId}</span>
                </p>
              ) : null}
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" size="sm" onClick={handleRetry}>
              Retry
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => router.push("/data-connection")}>
              Back to data connection
            </Button>
          </div>
        </div>
      )}

      {loading && !templateProposal && (
        <div className="bg-card rounded-2xl border border-border p-10 flex flex-col items-center justify-center gap-3 text-on-surface-variant">
          <span
            className="material-symbols-outlined text-3xl animate-spin"
            style={{ animationDuration: "1.2s" }}
            aria-hidden
          >
            progress_activity
          </span>
          <p className="text-sm font-medium text-on-surface">Running ingestion…</p>
          <p className="text-xs text-on-surface-variant text-center max-w-md">
            Building DDL and preview from the connector. This is synchronous on the API.
          </p>
        </div>
      )}

      {templateProposal && (
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">
          <div className="flex flex-col gap-4">
            <div className="bg-card rounded-2xl border border-border p-5 flex flex-col gap-4">
              <div className="flex items-center justify-between gap-4 flex-wrap">
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
                  <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium">
                    Standard
                  </span>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider w-24">
                        Field
                      </th>
                      <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider w-24">
                        Type
                      </th>
                      <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider w-24">
                        Mode
                      </th>
                      <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider w-48">
                        Description
                      </th>
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

            {templateProposal.ddl ? (
              <div className="bg-card rounded-2xl border border-border p-5 flex flex-col gap-3">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">DDL</p>
                  <button
                    type="button"
                    onClick={() => void copyDDL()}
                    className="text-xs font-semibold text-primary hover:underline"
                  >
                    {copied ? "Copied" : "Copy DDL"}
                  </button>
                </div>
                <pre className="text-xs font-mono bg-muted/50 border border-border rounded-xl p-4 overflow-x-auto max-h-72 overflow-y-auto whitespace-pre-wrap break-words">
                  {templateProposal.ddl}
                </pre>
              </div>
            ) : null}

            {previewRows.length > 0 && previewCols.length > 0 ? (
              <div className="bg-card rounded-2xl border border-border p-5 flex flex-col gap-3">
                <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
                  Row preview
                </p>
                <p className="text-xs text-on-surface-variant">
                  Showing {previewRows.length} row{previewRows.length === 1 ? "" : "s"}
                  {runResult != null && typeof runResult.row_count === "number"
                    ? ` (${runResult.row_count} total reported by run)`
                    : ""}
                  .
                </p>
                <div className="overflow-x-auto max-h-80 overflow-y-auto rounded-xl border border-border">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-muted/80 backdrop-blur-sm z-[1]">
                      <tr>
                        {previewCols.map((c) => (
                          <th
                            key={c}
                            className="text-left py-2 px-2 font-semibold text-on-surface-variant whitespace-nowrap border-b border-border"
                          >
                            {c}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {previewRows.map((row, i) => (
                        <tr key={i} className="border-b border-border/50">
                          {previewCols.map((c) => (
                            <td key={c} className="py-1.5 px-2 font-mono text-on-surface max-w-[220px] truncate" title={cellPreview(row[c])}>
                              {cellPreview(row[c])}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </div>

          <div className="flex flex-col gap-4">
            <div className="bg-card rounded-2xl border border-border p-5 flex flex-col gap-3">
              <div>
                <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-1">Connector</p>
                <p className="text-sm font-semibold text-on-surface">{connectorName}</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-1">
                  Selected fields
                </p>
                <p className="text-sm font-semibold text-on-surface">{columns.length}</p>
              </div>
              <div>
                <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-1">Table</p>
                <code className="text-xs font-mono text-primary">{templateProposal.tableName}</code>
              </div>
              {runResult != null && (
                <div>
                  <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-1">Run</p>
                  <p className="text-xs text-on-surface">
                    Rows: <span className="font-semibold">{runResult.row_count}</span>
                  </p>
                  {runResult.errors.length > 0 ? (
                    <ul className="text-xs text-amber-800 mt-2 list-disc pl-4 space-y-1">
                      {runResult.errors.map((e, i) => (
                        <li key={i}>{e}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              )}
            </div>

            <div className="bg-card rounded-2xl border border-border p-5">
              <div className="flex items-start gap-2 mb-2">
                <span className="material-symbols-outlined text-primary text-base mt-0.5">info</span>
                <p className="text-xs font-semibold text-on-surface">Summary</p>
              </div>
              <p className="text-xs text-on-surface-variant leading-relaxed">
                DDL and column list come from the ingestion run. Save the template to use it in Data Export.
              </p>
            </div>

            {!saved && (
              <div className="bg-card rounded-2xl border border-border p-5 flex flex-col gap-2">
                <Label
                  htmlFor="template-save-name"
                  className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider"
                >
                  Template name
                </Label>
                <Input
                  id="template-save-name"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  className="font-mono text-sm"
                  placeholder="Table name in warehouse"
                />
                <p className="text-xs text-on-surface-variant">You can rename before saving. Defaults to the run output.</p>
              </div>
            )}

            {saved ? (
              <div className="flex flex-col gap-2">
                <div className="w-full py-3 px-4 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center gap-2 text-emerald-800 text-sm font-semibold">
                  <span className="material-symbols-outlined text-base">check_circle</span>
                  Template saved
                </div>
                <p className="text-xs text-on-surface-variant text-center">
                  <code className="font-mono">{templateName.trim() || templateProposal.tableName}</code> is ready to use.
                </p>
                <button
                  type="button"
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
                  type="button"
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
