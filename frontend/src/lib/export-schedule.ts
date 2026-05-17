export type ExportFrequency = "hourly" | "daily" | "weekly" | "monthly"

export interface ExportSchedule {
  frequency: string
  time: string
  /** 0 = Sunday … 6 = Saturday (weekly). */
  dayOfWeek?: number
  /** 1–31 (monthly). */
  dayOfMonth?: number
}

export const WEEKDAY_OPTIONS = [
  { value: 0, label: "Sunday" },
  { value: 1, label: "Monday" },
  { value: 2, label: "Tuesday" },
  { value: 3, label: "Wednesday" },
  { value: 4, label: "Thursday" },
  { value: 5, label: "Friday" },
  { value: 6, label: "Saturday" },
] as const

export function formatScheduleSummary(schedule: ExportSchedule): string {
  const freq = schedule.frequency.charAt(0).toUpperCase() + schedule.frequency.slice(1)
  const parts = [freq, `@ ${schedule.time} UTC`]
  if (schedule.frequency === "weekly" && schedule.dayOfWeek != null) {
    const day = WEEKDAY_OPTIONS.find((d) => d.value === schedule.dayOfWeek)?.label
    if (day) parts.push(`on ${day}`)
  }
  if (schedule.frequency === "monthly" && schedule.dayOfMonth != null) {
    parts.push(`on day ${schedule.dayOfMonth}`)
  }
  return parts.join(" ")
}
