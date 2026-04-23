"use client"

import { useState } from "react"
import { useExportJobStore } from "@/lib/stores/exportJobStore"
import { useTemplateStore } from "@/lib/stores/templateStore"
import { cn } from "@/lib/utils"

const FREQUENCIES = [
  { id: "hourly",  label: "Hourly",  icon: "schedule" },
  { id: "daily",   label: "Daily",   icon: "today" },
  { id: "weekly",  label: "Weekly",  icon: "date_range" },
  { id: "monthly", label: "Monthly", icon: "calendar_month" },
] as const

interface ExportFormData {
  step1: { projectId: string; serviceAccountEmail: string }
  step2: { templateId: string; credentialId: string; tableName: string }
  step3: { frequency: string; time: string; scheduled: boolean }
}

interface Props {
  data: ExportFormData
  onUpdate: (data: Record<string, unknown>) => void
}

export default function ExportSchedulerStep({ data, onUpdate }: Props) {
  const { addJob } = useExportJobStore()
  const { templates } = useTemplateStore()
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(data.step3.scheduled)

  const selectedTemplate = templates.find((t) => t.id === data.step2.templateId)

  async function handleSchedule() {
    setSaving(true)
    await new Promise((r) => setTimeout(r, 1200))
    addJob({
      projectId:            data.step1.projectId,
      serviceAccountEmail:  data.step1.serviceAccountEmail,
      templateId:           data.step2.templateId,
      tableName:            data.step2.tableName,
      credentialId:         data.step2.credentialId,
      ddl:                  selectedTemplate?.ddl ?? "",
      schedule: {
        frequency: data.step3.frequency,
        time:      data.step3.time,
      },
    })
    onUpdate({ scheduled: true })
    setSaving(false)
    setSaved(true)
  }

  return (
    <div className="space-y-6 max-w-[800px]">
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">Schedule Export</h1>
        <p className="text-sm text-on-surface-variant mt-0.5">
          Configure how often this extraction runs.
        </p>
      </div>

      {/* Summary */}
      <div className="bg-muted rounded-2xl p-5 flex flex-col gap-2 text-sm">
        <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-1">Export summary</p>
        <div className="flex gap-2">
          <span className="text-on-surface-variant w-28 flex-shrink-0">Template</span>
          <code className="text-primary font-mono text-xs">{selectedTemplate?.tableName ?? "—"}</code>
        </div>
        <div className="flex gap-2">
          <span className="text-on-surface-variant w-28 flex-shrink-0">Destination table</span>
          <code className="text-primary font-mono text-xs">{data.step2.tableName || "—"}</code>
        </div>
        <div className="flex gap-2">
          <span className="text-on-surface-variant w-28 flex-shrink-0">GCP Project</span>
          <span className="text-on-surface text-xs font-mono">{data.step1.projectId || "—"}</span>
        </div>
      </div>

      {/* Frequency */}
      <div className="flex flex-col gap-3">
        <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">Frequency</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {FREQUENCIES.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => onUpdate({ frequency: f.id })}
              className={cn(
                "flex flex-col items-center gap-2 p-4 rounded-xl border font-semibold text-sm transition-all",
                data.step3.frequency === f.id
                  ? "border-primary/40 bg-primary/5 text-primary"
                  : "border-border bg-card text-on-surface hover:border-primary/30"
              )}
            >
              <span className="material-symbols-outlined text-xl">{f.icon}</span>
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Time */}
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
          Start time (UTC)
        </label>
        <input
          type="time"
          value={data.step3.time}
          onChange={(e) => onUpdate({ time: e.target.value })}
          className="w-40 px-3 py-2 border border-border rounded-lg bg-background text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
        />
      </div>

      {/* CTA */}
      {saved ? (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm">
          <span className="material-symbols-outlined text-base">check_circle</span>
          <div>
            <p className="font-semibold">Export scheduled</p>
            <p className="text-xs mt-0.5">
              Runs <strong>{data.step3.frequency}</strong> at <strong>{data.step3.time} UTC</strong> · Table:{" "}
              <code className="font-mono">{data.step2.tableName}</code>
            </p>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={handleSchedule}
          disabled={saving || !data.step2.tableName || !data.step1.projectId}
          className="self-start px-5 py-2.5 bg-primary text-white rounded-xl font-semibold text-sm hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
        >
          <span className="material-symbols-outlined text-base">
            {saving ? "sync" : "schedule_send"}
          </span>
          {saving ? "Scheduling…" : "Schedule export"}
        </button>
      )}
    </div>
  )
}
