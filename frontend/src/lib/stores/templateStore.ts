import { create } from "zustand"
import { persist, createJSONStorage } from "zustand/middleware"
import type { TemplateColumn } from "@/lib/stores/connectorStore"

export interface SavedTemplate {
  id: string
  tableName: string
  platform: string
  endpoint: string
  columns: TemplateColumn[]
  ddl: string
  savedAt: string
}

interface TemplateStore {
  templates: SavedTemplate[]
  addTemplate: (template: Omit<SavedTemplate, "id" | "savedAt">) => void
  deleteTemplate: (id: string) => void
  updateTemplate: (id: string, updates: Partial<SavedTemplate>) => void
}

export const useTemplateStore = create<TemplateStore>()(
  persist(
    (set) => ({
      templates: [],
      addTemplate: (template) =>
        set((state) => ({
          templates: [
            ...state.templates,
            {
              ...template,
              id: crypto.randomUUID(),
              savedAt: new Date().toISOString(),
            },
          ],
        })),
      deleteTemplate: (id) =>
        set((state) => ({
          templates: state.templates.filter((t) => t.id !== id),
        })),
      updateTemplate: (id, updates) =>
        set((state) => ({
          templates: state.templates.map((t) =>
            t.id === id ? { ...t, ...updates } : t
          ),
        })),
    }),
    {
      name: "templates-storage",
      storage: createJSONStorage(() =>
        typeof window !== "undefined"
          ? localStorage
          : { getItem: () => null, setItem: () => {}, removeItem: () => {} }
      ),
    }
  )
)
