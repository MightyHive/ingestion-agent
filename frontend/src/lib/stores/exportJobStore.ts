import { create } from "zustand"
import { persist, createJSONStorage } from "zustand/middleware"
import type { ExportSchedule } from "@/lib/export-schedule"

export interface ExportRunPreview {
  columns: string[]
  rows: Record<string, unknown>[]
  targetTable: string
}

export interface ExportRunRecord {
  id: string
  ranAt: string
  status: "success" | "failed"
  durationSec: number
  rowCount: number
  requestId?: string
  error?: string
  /** Sample rows from the API (persisted locally for dev / QA). */
  preview?: ExportRunPreview
}

export interface ExportJob {
  id: string
  projectId: string
  serviceAccountEmail: string
  templateId: string
  credentialIds: string[]
  tableNames: Record<string, string>
  ddl: string
  schedule: ExportSchedule
  refreshWindowDays: number
  createdAt: string
  /** Recent ingestion runs triggered from Export Planner (newest first). */
  lastRuns?: ExportRunRecord[]
}

interface ExportJobStore {
  jobs: ExportJob[]
  addJob: (job: Omit<ExportJob, "id" | "createdAt">) => void
  deleteJob: (id: string) => void
  updateJob: (id: string, updates: Partial<ExportJob>) => void
  appendRun: (jobId: string, run: Omit<ExportRunRecord, "id" | "ranAt">) => void
}

export const useExportJobStore = create<ExportJobStore>()(
  persist(
    (set) => ({
      jobs: [],
      addJob: (job) =>
        set((state) => ({
          jobs: [
            ...state.jobs,
            { ...job, id: crypto.randomUUID(), createdAt: new Date().toISOString() },
          ],
        })),
      deleteJob: (id) =>
        set((state) => ({ jobs: state.jobs.filter((j) => j.id !== id) })),
      updateJob: (id, updates) =>
        set((state) => ({
          jobs: state.jobs.map((j) => (j.id === id ? { ...j, ...updates } : j)),
        })),
      appendRun: (jobId, run) =>
        set((state) => ({
          jobs: state.jobs.map((j) => {
            if (j.id !== jobId) return j
            const record: ExportRunRecord = {
              ...run,
              id: crypto.randomUUID(),
              ranAt: new Date().toISOString(),
            }
            const prev = j.lastRuns ?? []
            return { ...j, lastRuns: [record, ...prev].slice(0, 20) }
          }),
        })),
    }),
    {
      name: "export-jobs-storage",
      storage: createJSONStorage(() =>
        typeof window !== "undefined"
          ? localStorage
          : { getItem: () => null, setItem: () => {}, removeItem: () => {} }
      ),
    }
  )
)
