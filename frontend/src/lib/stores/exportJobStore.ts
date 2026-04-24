import { create } from "zustand"
import { persist, createJSONStorage } from "zustand/middleware"

export interface ExportJob {
  id: string
  projectId: string
  serviceAccountEmail: string
  templateId: string
  tableName: string
  credentialId: string
  ddl: string
  schedule: { frequency: string; time: string }
  createdAt: string
}

interface ExportJobStore {
  jobs: ExportJob[]
  addJob: (job: Omit<ExportJob, "id" | "createdAt">) => void
  deleteJob: (id: string) => void
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
