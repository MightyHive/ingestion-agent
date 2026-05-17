"use client"

import type { ExportSchedule } from "@/lib/export-schedule"
import { WEEKDAY_OPTIONS } from "@/lib/export-schedule"

type Props = {
  schedule: ExportSchedule
  onChange: (patch: Partial<ExportSchedule>) => void
  labelClass?: string
  inputClass?: string
}

export default function ScheduleFields({
  schedule,
  onChange,
  labelClass = "text-xs font-semibold text-on-surface-variant uppercase tracking-wider",
  inputClass = "w-40 px-3 py-2 border border-border rounded-lg bg-background text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20",
}: Props) {
  const freq = schedule.frequency.toLowerCase()

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <label className={labelClass}>Start time (UTC)</label>
        <input
          type="time"
          value={schedule.time}
          onChange={(e) => onChange({ time: e.target.value })}
          className={inputClass}
        />
      </div>

      {freq === "weekly" ? (
        <div className="flex flex-col gap-1.5">
          <label className={labelClass}>Day of week</label>
          <select
            className="w-full max-w-xs px-3 py-2 border border-border rounded-lg bg-background text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
            value={schedule.dayOfWeek ?? 1}
            onChange={(e) => onChange({ dayOfWeek: parseInt(e.target.value, 10) })}
          >
            {WEEKDAY_OPTIONS.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </div>
      ) : null}

      {freq === "monthly" ? (
        <div className="flex flex-col gap-1.5">
          <label className={labelClass}>Day of month</label>
          <input
            type="number"
            min={1}
            max={31}
            value={schedule.dayOfMonth ?? 1}
            onChange={(e) =>
              onChange({ dayOfMonth: Math.min(31, Math.max(1, parseInt(e.target.value, 10) || 1)) })
            }
            className={inputClass}
          />
          <p className="text-xs text-muted-foreground">Runs on this calendar day each month (1–31).</p>
        </div>
      ) : null}
    </div>
  )
}
