"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { Button, buttonVariants } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import RunPreviewDialog from "@/components/export-planner/RunPreviewDialog"
import ScheduleFields from "@/components/data-export/ScheduleFields"
import { runTemplateIngestion, type TemplateRunResult } from "@/lib/export-ingestion"
import { formatScheduleSummary, type ExportSchedule } from "@/lib/export-schedule"
import { useExportJobStore, type ExportJob, type ExportRunRecord } from "@/lib/stores/exportJobStore"
import { useTemplateStore } from "@/lib/stores/templateStore"
import { fetchCredentials, decodeName, type BackendConnection } from "@/lib/api/credentials"
import { useTenantStore } from "@/lib/stores/tenantStore"

const FREQUENCIES = ["hourly", "daily", "weekly", "monthly"]

function platformRefreshDefault(platform: string, templateName = ""): number {
  const s = `${platform} ${templateName}`.toLowerCase()
  if (s.includes("meta") || s.includes("facebook")) return 7
  if (s.includes("tiktok")) return 7
  if (s.includes("google")) return 3
  return 1
}

type ActionNote = { kind: "success" | "error"; message: string }

function runsForJob(job: ExportJob): Array<{
  id: string
  date: Date
  status: "success" | "failed"
  duration: number
  rows: number
  requestId?: string
  error?: string
  hasPreview?: boolean
}> {
  const stored = job.lastRuns ?? []
  if (stored.length > 0) {
    return stored.map((r) => ({
      id: r.id,
      date: new Date(r.ranAt),
      status: r.status,
      duration: r.durationSec,
      rows: r.rowCount,
      requestId: r.requestId,
      error: r.error,
      hasPreview: Boolean(r.preview?.rows?.length),
    }))
  }
  return []
}

export default function ExportPlannerPage() {
  const { jobs, deleteJob, updateJob, appendRun } = useExportJobStore()
  const { templates, updateTemplate } = useTemplateStore()
  const selectedTenantId = useTenantStore((s) => s.selectedTenantId)
  const [allConnections, setAllConnections] = useState<BackendConnection[]>([])

  const [runningId, setRunningId] = useState<string | null>(null)
  const [actionNote, setActionNote] = useState<ActionNote | null>(null)
  const [rerunningId, setRerunningId] = useState<string | null>(null)

  // Backfill
  const [backfillFor, setBackfillFor] = useState<ExportJob | null>(null)
  const [backfillStart, setBackfillStart] = useState("")
  const [backfillEnd, setBackfillEnd] = useState("")
  const [backfillError, setBackfillError] = useState<string | null>(null)
  const [backfillBusy, setBackfillBusy] = useState(false)

  // Edit
  const [editFor, setEditFor] = useState<ExportJob | null>(null)
  const [editFreq, setEditFreq] = useState("")
  const [editTime, setEditTime] = useState("")
  const [editRefreshWindow, setEditRefreshWindow] = useState<number>(1)
  const [editConnectionId, setEditConnectionId] = useState<string>("")
  const [editSchedule, setEditSchedule] = useState<ExportSchedule>({
    frequency: "daily",
    time: "00:00",
  })

  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewResult, setPreviewResult] = useState<TemplateRunResult | null>(null)
  const [previewTemplateName, setPreviewTemplateName] = useState("")

  // Last runs expanded per job
  const [expandedJobs, setExpandedJobs] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (!selectedTenantId) return
    fetchCredentials(selectedTenantId)
      .then((all) => setAllConnections(all.filter((c) => c.status === "active")))
      .catch(() => setAllConnections([]))
  }, [selectedTenantId])

  const sorted = useMemo(
    () => [...jobs].sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()),
    [jobs]
  )

  function getTemplate(templateId: string) {
    return templates.find((t) => t.id === templateId)
  }

  function openPreview(result: TemplateRunResult, templateName: string) {
    setPreviewResult(result)
    setPreviewTemplateName(templateName)
    setPreviewOpen(true)
  }

  function previewFromRunRecord(run: ExportRunRecord, templateName: string, rowCount: number) {
    if (!run.preview) return
    openPreview(
      {
        row_count: rowCount,
        target_table: run.preview.targetTable,
        requestId: run.requestId ?? null,
        errors: [],
        columns: run.preview.columns,
        rows_preview: run.preview.rows,
      },
      templateName
    )
  }

  async function executeRun(
    job: ExportJob,
    options: Parameters<typeof runTemplateIngestion>[1]
  ): Promise<TemplateRunResult | null> {
    const tmpl = getTemplate(job.templateId)
    if (!tmpl) {
      setActionNote({ kind: "error", message: "Template not found. Re-create the export from Data Export." })
      return null
    }

    const t0 = performance.now()
    try {
      const result = await runTemplateIngestion(tmpl, options)
      const durationSec = Math.max(1, Math.round((performance.now() - t0) / 1000))
      const runPayload: Omit<ExportRunRecord, "id" | "ranAt"> = {
        status: "success",
        durationSec,
        rowCount: result.row_count,
        requestId: result.requestId ?? undefined,
        preview:
          result.rows_preview.length > 0
            ? {
                columns: result.columns,
                rows: result.rows_preview,
                targetTable: result.target_table,
              }
            : undefined,
      }
      appendRun(job.id, runPayload)
      const warn =
        result.errors.length > 0 ? ` Warnings: ${result.errors.slice(0, 2).join("; ")}` : ""
      setActionNote({
        kind: "success",
        message: `Run OK · ${result.row_count.toLocaleString()} rows · ${tmpl.tableName}${warn}`,
      })
      openPreview(result, tmpl.tableName)
      return result
    } catch (e) {
      const durationSec = Math.max(1, Math.round((performance.now() - t0) / 1000))
      const err = e as Error & { requestId?: string | null }
      const message = err instanceof Error ? err.message : "Run failed"
      appendRun(job.id, {
        status: "failed",
        durationSec,
        rowCount: 0,
        requestId: err.requestId ?? undefined,
        error: message,
      })
      setActionNote({
        kind: "error",
        message: err.requestId ? `${message} (Request-ID: ${err.requestId})` : message,
      })
      return null
    }
  }

  async function handleRunNow(job: ExportJob) {
    setRunningId(job.id)
    setActionNote(null)
    const refreshDays = job.refreshWindowDays ?? platformRefreshDefault(
      getTemplate(job.templateId)?.platform ?? "",
      getTemplate(job.templateId)?.tableName ?? ""
    )
    try {
      await executeRun(job, { mode: "refresh", refreshWindowDays: refreshDays })
    } finally {
      setRunningId(null)
    }
  }

  function openBackfill(job: ExportJob) {
    setBackfillFor(job)
    setBackfillError(null)
    const end = new Date()
    const start = new Date()
    start.setDate(start.getDate() - 30)
    setBackfillStart(start.toISOString().slice(0, 10))
    setBackfillEnd(end.toISOString().slice(0, 10))
  }

  function closeBackfill() {
    setBackfillFor(null)
    setBackfillBusy(false)
    setBackfillError(null)
  }

  async function handleBackfillSubmit() {
    if (!backfillFor) return
    if (!backfillStart || !backfillEnd) { setBackfillError("Choose a start and end date."); return }
    if (backfillStart > backfillEnd) { setBackfillError("Start must be before or equal to end."); return }
    setBackfillBusy(true)
    setActionNote(null)
    const job = backfillFor
    try {
      await executeRun(job, {
        mode: "backfill",
        dateStart: backfillStart,
        dateEnd: backfillEnd,
      })
      closeBackfill()
    } finally {
      setBackfillBusy(false)
    }
  }

  function openEdit(job: ExportJob) {
    const tmpl = getTemplate(job.templateId)
    setEditFor(job)
    setEditFreq(job.schedule.frequency.toLowerCase())
    setEditTime(job.schedule.time)
    setEditSchedule({ ...job.schedule })
    setEditRefreshWindow(
      job.refreshWindowDays ?? platformRefreshDefault(tmpl?.platform ?? "", tmpl?.tableName ?? "")
    )
    setEditConnectionId(tmpl?.connectionId ?? "")
  }

  function closeEdit() { setEditFor(null) }

  function handleEditSave() {
    if (!editFor) return
    const schedule: ExportSchedule = {
      frequency: editFreq,
      time: editTime,
      ...(editFreq === "weekly" ? { dayOfWeek: editSchedule.dayOfWeek ?? 1 } : {}),
      ...(editFreq === "monthly" ? { dayOfMonth: editSchedule.dayOfMonth ?? 1 } : {}),
    }
    updateJob(editFor.id, {
      schedule,
      refreshWindowDays: editRefreshWindow,
    })
    // Persist connection change on the template itself
    const tmpl = getTemplate(editFor.templateId)
    if (tmpl) {
      updateTemplate(editFor.templateId, {
        connectionId: editConnectionId || undefined,
      })
    }
    setActionNote({
      kind: "success",
      message: `${formatScheduleSummary(schedule)} · ${editRefreshWindow}d refresh window`,
    })
    closeEdit()
  }

  function toggleExpanded(id: string) {
    setExpandedJobs((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  async function handleRerun(job: ExportJob, runId: string) {
    setRerunningId(runId)
    setActionNote(null)
    const refreshDays = job.refreshWindowDays ?? platformRefreshDefault(
      getTemplate(job.templateId)?.platform ?? "",
      getTemplate(job.templateId)?.tableName ?? ""
    )
    try {
      await executeRun(job, { mode: "refresh", refreshWindowDays: refreshDays })
    } finally {
      setRerunningId(null)
    }
  }

  return (
    <div className="space-y-8 p-6 max-w-[1200px]">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Export planner</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-lg">
            Manage your scheduled exports — trigger on-demand runs, backfill historical data, or edit an existing schedule.
          </p>
        </div>
        <Link
          href="/data-export"
          className={cn(buttonVariants(), "bg-[#5c27fe] hover:bg-[#4b1fd1] text-white shrink-0 h-10 px-4")}
        >
          <span className="material-symbols-outlined mr-2 text-[18px]">add</span>
          New schedule
        </Link>
      </div>

      {actionNote && (
        <p
          className={cn(
            "text-sm rounded-lg border px-4 py-2",
            actionNote.kind === "success"
              ? "border-emerald-200 bg-emerald-50 text-emerald-900"
              : "border-red-200 bg-red-50 text-red-900"
          )}
        >
          {actionNote.message}
        </p>
      )}

      <div className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Your scheduled exports</h2>

        {sorted.length === 0 ? (
          <p className="text-sm text-muted-foreground border rounded-xl p-6 bg-white">
            No exports yet. Use{" "}
            <Link className="text-primary underline" href="/data-export">
              Data Export
            </Link>{" "}
            to create one; it will appear here.
          </p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {sorted.map((job) => {
              const tmpl = getTemplate(job.templateId)
              const name = tmpl?.tableName ?? job.templateId
              const platform = tmpl?.platform ?? ""
              const fieldCount = tmpl?.columns.length ?? 0
              const refreshDays = job.refreshWindowDays ?? platformRefreshDefault(platform, tmpl?.tableName ?? "")
              const expanded = expandedJobs.has(job.id)
              const runs = runsForJob(job)

              return (
                <div key={job.id} className="bg-white rounded-2xl border p-5 flex flex-col gap-4">
                  {/* Header */}
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold text-base leading-tight">{name}</div>
                      <div className="text-sm text-muted-foreground mt-1">
                        {fieldCount} {fieldCount === 1 ? "field" : "fields"} &bull;{" "}
                        {formatScheduleSummary(job.schedule)}
                        {platform && <span className="ml-2">&bull; {platform}</span>}
                      </div>
                      <div className="text-xs text-muted-foreground mt-0.5">
                        Refresh window: {refreshDays} {refreshDays === 1 ? "day" : "days"}
                      </div>
                      {tmpl?.connectionId && (() => {
                        const conn = allConnections.find((c) => c.connection_id === tmpl.connectionId)
                        const label = conn ? (decodeName(conn.name).name || conn.connection_id) : tmpl.connectionId
                        return (
                          <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1">
                            <span className="material-symbols-outlined text-[13px]">vpn_key</span>
                            {label}
                          </div>
                        )
                      })()}
                    </div>
                    {platform && (
                      <span className="shrink-0 text-[11px] font-semibold tracking-wider border rounded-full px-2.5 py-0.5 text-muted-foreground uppercase">
                        {platform}
                      </span>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={runningId === job.id}
                      onClick={() => void handleRunNow(job)}
                      className="h-8"
                      style={{ backgroundColor: "#5c27fe", color: "white" }}
                    >
                      {runningId === job.id ? "Running…" : "Run now"}
                    </Button>
                    <Button size="sm" variant="outline" className="h-8" onClick={() => openBackfill(job)}>
                      Backfill
                    </Button>
                    <Button size="sm" variant="outline" className="h-8" onClick={() => openEdit(job)}>
                      Edit schedule
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-8 text-destructive ml-auto"
                      onClick={() => {
                        if (confirm("Remove this scheduled export?")) deleteJob(job.id)
                      }}
                    >
                      Remove
                    </Button>
                  </div>

                  {/* Last runs */}
                  <div>
                    <button
                      className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground hover:text-foreground transition-colors"
                      onClick={() => toggleExpanded(job.id)}
                    >
                      <span className="material-symbols-outlined text-[15px]">
                        {expanded ? "expand_less" : "expand_more"}
                      </span>
                      Last runs
                      {runs.length > 0 ? ` (${runs.length})` : ""}
                    </button>

                    {expanded && (
                      <div className="mt-2 rounded-xl border overflow-hidden">
                        {runs.length === 0 ? (
                          <p className="px-3 py-4 text-xs text-muted-foreground">
                            No runs yet. Use Run now to fetch data from the connector.
                          </p>
                        ) : (
                        runs.map((run) => (
                          <div
                            key={run.id}
                            className="flex items-center gap-3 px-3 py-2 text-xs border-b last:border-0 hover:bg-muted/30"
                          >
                            <span className="text-muted-foreground w-[86px] shrink-0">
                              {run.date.toLocaleDateString()}
                            </span>
                            <span
                              className={cn(
                                "font-semibold w-[48px] shrink-0",
                                run.status === "success" ? "text-emerald-600" : "text-destructive"
                              )}
                            >
                              {run.status === "success" ? "OK" : "Failed"}
                            </span>
                            <span className="text-muted-foreground w-[34px] shrink-0">{run.duration}s</span>
                            <span className="text-muted-foreground flex-1 min-w-0 truncate">
                              {run.status === "success"
                                ? `${run.rows.toLocaleString()} rows`
                                : run.error ?? "—"}
                            </span>
                            {run.hasPreview ? (
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-6 px-2 text-[11px] shrink-0"
                                onClick={() => {
                                  const stored = job.lastRuns?.find((r) => r.id === run.id)
                                  if (stored) previewFromRunRecord(stored, name, run.rows)
                                }}
                              >
                                Sample
                              </Button>
                            ) : null}
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-6 px-2 text-[11px] shrink-0"
                              disabled={rerunningId === run.id || runningId === job.id}
                              onClick={() => void handleRerun(job, run.id)}
                            >
                              {rerunningId === run.id ? "…" : "Re-run"}
                            </Button>
                          </div>
                        ))
                        )}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Backfill dialog */}
      <Dialog open={backfillFor !== null} onOpenChange={(open) => { if (!open) closeBackfill() }}>
        <DialogContent className="sm:max-w-md bg-white">
          <DialogHeader>
            <DialogTitle>Backfill</DialogTitle>
            <p className="text-sm text-muted-foreground">
              {backfillFor
                ? (getTemplate(backfillFor.templateId)?.tableName ?? backfillFor.templateId)
                : ""}{" "}
              — choose a date range to re-ingest historical data.
            </p>
          </DialogHeader>
          {backfillFor && (
            <>
              <div className="grid gap-4 py-2">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Start date</label>
                  <Input type="date" value={backfillStart} onChange={(e) => setBackfillStart(e.target.value)} />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">End date</label>
                  <Input type="date" value={backfillEnd} onChange={(e) => setBackfillEnd(e.target.value)} />
                </div>
              </div>
              {backfillError && <p className="text-sm text-destructive">{backfillError}</p>}
              <DialogFooter>
                <Button variant="outline" onClick={closeBackfill}>Cancel</Button>
                <Button className="bg-[#5c27fe]" disabled={backfillBusy} onClick={() => void handleBackfillSubmit()}>
                  {backfillBusy ? "Running…" : "Run backfill"}
                </Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Edit schedule dialog */}
      <Dialog open={editFor !== null} onOpenChange={(open) => { if (!open) closeEdit() }}>
        <DialogContent className="sm:max-w-sm bg-white">
          <DialogHeader>
            <DialogTitle>Edit schedule</DialogTitle>
            <p className="text-sm text-muted-foreground">
              {editFor ? (getTemplate(editFor.templateId)?.tableName ?? editFor.templateId) : ""}
            </p>
          </DialogHeader>
          {editFor && (
            <>
              <div className="grid gap-4 py-2">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Frequency</label>
                  <select
                    className="w-full border rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-ring"
                    value={editFreq}
                    onChange={(e) => {
                      const next = e.target.value
                      setEditFreq(next)
                      setEditSchedule((s) => ({
                        ...s,
                        frequency: next,
                        ...(next === "weekly" && s.dayOfWeek == null ? { dayOfWeek: 1 } : {}),
                        ...(next === "monthly" && s.dayOfMonth == null ? { dayOfMonth: 1 } : {}),
                      }))
                    }}
                  >
                    {FREQUENCIES.map((f) => (
                      <option key={f} value={f}>
                        {f.charAt(0).toUpperCase() + f.slice(1)}
                      </option>
                    ))}
                  </select>
                </div>
                <ScheduleFields
                  schedule={{
                    frequency: editFreq,
                    time: editTime,
                    dayOfWeek: editSchedule.dayOfWeek,
                    dayOfMonth: editSchedule.dayOfMonth,
                  }}
                  labelClass="text-xs font-medium text-muted-foreground"
                  onChange={(patch) => {
                    if (patch.time != null) setEditTime(patch.time)
                    setEditSchedule((s) => ({
                      ...s,
                      ...patch,
                      frequency: editFreq,
                      time: patch.time ?? editTime,
                    }))
                  }}
                />
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">
                    Refresh window (days)
                  </label>
                  <p className="text-[11px] text-muted-foreground -mt-0.5">
                    Each run will re-fetch this many days back to catch retroactive updates.
                  </p>
                  <Input
                    type="number"
                    min={1}
                    max={90}
                    value={editRefreshWindow}
                    onChange={(e) => setEditRefreshWindow(Math.max(1, parseInt(e.target.value) || 1))}
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Credentials</label>
                  <select
                    className="w-full border rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-ring"
                    value={editConnectionId}
                    onChange={(e) => setEditConnectionId(e.target.value)}
                  >
                    <option value="">— None —</option>
                    {(() => {
                      const tmpl = getTemplate(editFor!.templateId)
                      const platform = tmpl?.platform ?? ""
                      const filtered = platform
                        ? allConnections.filter((c) => c.provider.toLowerCase() === platform.toLowerCase())
                        : allConnections
                      return filtered.map((c) => {
                        const label = decodeName(c.name).name || c.connection_id
                        return (
                          <option key={c.connection_id} value={c.connection_id}>
                            {label} ({c.connection_id})
                          </option>
                        )
                      })
                    })()}
                  </select>
                  <p className="text-[11px] text-muted-foreground">
                    The Cloud Function will use this connection to read secrets from Secret Manager.
                  </p>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={closeEdit}>Cancel</Button>
                <Button className="bg-[#5c27fe]" onClick={handleEditSave}>Save</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      <RunPreviewDialog
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        result={previewResult}
        templateName={previewTemplateName}
      />
    </div>
  )
}
