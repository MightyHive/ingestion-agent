"use client"

import { useMemo, useState } from "react"
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
import { useExportJobStore, type ExportJob } from "@/lib/stores/exportJobStore"
import { useTemplateStore } from "@/lib/stores/templateStore"

const FREQUENCIES = ["hourly", "daily", "weekly", "monthly"]

const FREQ_MS: Record<string, number> = {
  hourly: 3_600_000,
  daily: 86_400_000,
  weekly: 604_800_000,
  monthly: 2_592_000_000,
}

function seededRand(seed: string, i: number) {
  let h = 0
  for (let c = 0; c < seed.length; c++) h = (Math.imul(31, h) + seed.charCodeAt(c)) | 0
  h = Math.imul(h ^ (i + 1), 2654435761) | 0
  return Math.abs(h % 1000) / 1000
}

function generateRuns(job: ExportJob, n = 7) {
  const ms = FREQ_MS[job.schedule.frequency.toLowerCase()] ?? FREQ_MS.daily
  return Array.from({ length: n }, (_, i) => ({
    id: `${job.id}-r${i}`,
    date: new Date(Date.now() - ms * (i + 1)),
    status: seededRand(job.id, i) > 0.12 ? ("success" as const) : ("failed" as const),
    duration: Math.round(4 + seededRand(job.id + "d", i) * 28),
    rows: seededRand(job.id, i) > 0.12 ? Math.round(800 + seededRand(job.id + "r", i) * 48000) : 0,
  }))
}

export default function ExportPlannerPage() {
  const { jobs, deleteJob, updateJob } = useExportJobStore()
  const { templates } = useTemplateStore()

  const [runningId, setRunningId] = useState<string | null>(null)
  const [actionNote, setActionNote] = useState<string | null>(null)

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

  // Last runs expanded per job
  const [expandedJobs, setExpandedJobs] = useState<Set<string>>(new Set())

  const sorted = useMemo(
    () => [...jobs].sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()),
    [jobs]
  )

  function getTemplate(templateId: string) {
    return templates.find((t) => t.id === templateId)
  }

  async function handleRunNow(job: ExportJob) {
    setRunningId(job.id)
    setActionNote(null)
    await new Promise((r) => setTimeout(r, 900))
    setRunningId(null)
    setActionNote(`Run queued: ${getTemplate(job.templateId)?.tableName ?? job.templateId}`)
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

  function handleBackfillSubmit() {
    if (!backfillFor) return
    if (!backfillStart || !backfillEnd) { setBackfillError("Choose a start and end date."); return }
    if (backfillStart > backfillEnd) { setBackfillError("Start must be before or equal to end."); return }
    setBackfillBusy(true)
    const job = backfillFor
    const name = getTemplate(job.templateId)?.tableName ?? job.templateId
    const t0 = backfillStart
    const t1 = backfillEnd
    window.setTimeout(() => {
      setBackfillBusy(false)
      setActionNote(`Backfill queued: ${name} · ${t0} → ${t1}`)
      closeBackfill()
    }, 800)
  }

  function openEdit(job: ExportJob) {
    setEditFor(job)
    setEditFreq(job.schedule.frequency.toLowerCase())
    setEditTime(job.schedule.time)
  }

  function closeEdit() { setEditFor(null) }

  function handleEditSave() {
    if (!editFor) return
    updateJob(editFor.id, { schedule: { frequency: editFreq, time: editTime } })
    setActionNote(`Schedule updated to ${editFreq} @ ${editTime} UTC`)
    closeEdit()
  }

  function toggleExpanded(id: string) {
    setExpandedJobs((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function handleRerun(name: string, date: Date) {
    setActionNote(`Re-run queued: ${name} (${date.toLocaleDateString()})`)
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
        <p className="text-sm rounded-lg border border-emerald-200 bg-emerald-50 text-emerald-900 px-4 py-2">
          {actionNote}
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
              const expanded = expandedJobs.has(job.id)
              const runs = generateRuns(job)

              return (
                <div key={job.id} className="bg-white rounded-2xl border p-5 flex flex-col gap-4">
                  {/* Header */}
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-semibold text-base leading-tight">{name}</div>
                      <div className="text-sm text-muted-foreground mt-1">
                        {fieldCount} {fieldCount === 1 ? "field" : "fields"} &bull;{" "}
                        {job.schedule.frequency.charAt(0).toUpperCase() + job.schedule.frequency.slice(1)}
                        {platform && (
                          <span className="ml-2 text-xs">
                            &bull; {platform}
                          </span>
                        )}
                      </div>
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
                    >
                      {runningId === job.id ? "…" : "Run now"}
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
                    </button>

                    {expanded && (
                      <div className="mt-2 rounded-xl border overflow-hidden">
                        {runs.map((run) => (
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
                            <span className="text-muted-foreground flex-1">
                              {run.status === "success" ? `${run.rows.toLocaleString()} rows` : "—"}
                            </span>
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-6 px-2 text-[11px] shrink-0"
                              onClick={() => handleRerun(name, run.date)}
                            >
                              Re-run
                            </Button>
                          </div>
                        ))}
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
                <Button className="bg-[#5c27fe]" disabled={backfillBusy} onClick={handleBackfillSubmit}>
                  {backfillBusy ? "Queueing…" : "Queue backfill"}
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
                    onChange={(e) => setEditFreq(e.target.value)}
                  >
                    {FREQUENCIES.map((f) => (
                      <option key={f} value={f}>
                        {f.charAt(0).toUpperCase() + f.slice(1)}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">Time (UTC)</label>
                  <Input type="time" value={editTime} onChange={(e) => setEditTime(e.target.value)} />
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
    </div>
  )
}
