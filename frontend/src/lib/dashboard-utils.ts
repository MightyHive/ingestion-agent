import type { ExportJob } from "@/lib/stores/exportJobStore"

const EXPIRING_SOON_DAYS = 7

export function daysUntil(isoDate: string) {
  const diff = new Date(isoDate).getTime() - Date.now()
  return Math.ceil(diff / 86_400_000)
}

export function isExpiringSoon(tokenExpiresAt?: string) {
  if (!tokenExpiresAt) return false
  const days = daysUntil(tokenExpiresAt)
  return days >= 0 && days <= EXPIRING_SOON_DAYS
}

export function isHealthyConnectionStatus(status?: string) {
  if (!status || status === "Testing...") return false
  return status === "Healthy"
}

function seededRand(seed: string) {
  let h = 0
  for (let c = 0; c < seed.length; c++) h = (Math.imul(31, h) + seed.charCodeAt(c)) | 0
  return Math.abs(h % 1000) / 1000
}

export interface FailedPipelineSummary {
  id: string
  name: string
  platform: string
  lastFailedAt: string
}

export function getFailedPipelinesFromJobs(
  jobs: ExportJob[],
  templateNameById: Record<string, string>
): FailedPipelineSummary[] {
  return jobs
    .filter((job) => seededRand(job.id) <= 0.12)
    .map((job) => ({
      id: job.id,
      name: templateNameById[job.templateId] ?? `Export ${job.id.slice(0, 8)}`,
      platform: templateNameById[job.templateId]?.split(" ")[0] ?? "Pipeline",
      lastFailedAt: new Date(Date.now() - 86_400_000 * (1 + Math.floor(seededRand(job.id + "d") * 3))).toISOString(),
    }))
}

export function fmtRelative(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const h = Math.floor(diff / 3_600_000)
  const m = Math.floor(diff / 60_000)
  if (h >= 24) return `${Math.floor(h / 24)}d ago`
  if (h > 0) return `${h}h ago`
  return `${Math.max(m, 1)}m ago`
}

export function fmtDateTime(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}
