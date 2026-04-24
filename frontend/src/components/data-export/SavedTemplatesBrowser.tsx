"use client"

import { useState } from "react"
import { useTemplateStore, type SavedTemplate } from "@/lib/stores/templateStore"
import { cn } from "@/lib/utils"

const PLATFORM_LABELS: Record<string, string> = {
  meta: "Meta",
  tiktok: "TikTok",
  youtube: "YouTube",
  google_ads: "Google Ads",
  dv360: "DV360",
}

interface Props {
  mode: "picker" | "browser"
  selectedId?: string
  onSelect?: (template: SavedTemplate) => void
}

export default function SavedTemplatesBrowser({ mode, selectedId, onSelect }: Props) {
  const { templates, deleteTemplate } = useTemplateStore()
  const [platformFilter, setPlatformFilter] = useState("all")

  const platforms = ["all", ...Array.from(new Set(templates.map((t) => t.platform)))]

  const filtered =
    platformFilter === "all" ? templates : templates.filter((t) => t.platform === platformFilter)

  if (templates.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3 text-on-surface-variant">
        <span className="material-symbols-outlined text-4xl">folder_open</span>
        <p className="text-sm">No saved templates yet.</p>
        <p className="text-xs">Complete a Data Connection flow and save a template first.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-1 p-1 bg-muted rounded-xl flex-wrap">
        {platforms.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setPlatformFilter(p)}
            className={cn(
              "flex-1 min-w-[72px] px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
              platformFilter === p
                ? "bg-white text-on-surface shadow-sm"
                : "text-on-surface-variant hover:text-on-surface"
            )}
          >
            {p === "all" ? "All" : (PLATFORM_LABELS[p] ?? p)}
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-2">
        {filtered.length === 0 && (
          <p className="text-sm text-on-surface-variant text-center py-8">No templates for this platform.</p>
        )}
        {filtered.map((t) => {
          const isSelected = selectedId === t.id
          return (
            <div
              key={t.id}
              className={cn(
                "flex items-center gap-4 p-4 rounded-xl border transition-all",
                isSelected
                  ? "border-primary/40 bg-primary/5"
                  : "border-border bg-card hover:bg-muted/40"
              )}
            >
              <span className="material-symbols-outlined text-on-surface-variant text-xl">table_chart</span>
              <div className="flex-1 min-w-0">
                <code className="text-sm font-mono font-semibold text-primary">{t.tableName}</code>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-xs text-on-surface-variant">
                    {PLATFORM_LABELS[t.platform] ?? t.platform} · {t.endpoint}
                  </span>
                  <span className="text-xs text-on-surface-variant">·</span>
                  <span className="text-xs text-on-surface-variant">{t.columns.length} fields</span>
                </div>
                <p className="text-xs text-on-surface-variant mt-0.5">
                  Saved {new Date(t.savedAt).toLocaleDateString()}
                </p>
              </div>

              <div className="flex items-center gap-2 flex-shrink-0">
                {mode === "picker" && (
                  <button
                    type="button"
                    onClick={() => onSelect?.(t)}
                    className={cn(
                      "px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors",
                      isSelected
                        ? "bg-primary text-white"
                        : "bg-primary/10 text-primary hover:bg-primary/20"
                    )}
                  >
                    {isSelected ? "Selected" : "Select"}
                  </button>
                )}
                {mode === "browser" && (
                  <button
                    type="button"
                    onClick={() => deleteTemplate(t.id)}
                    className="p-1.5 rounded-lg text-on-surface-variant hover:text-red-600 hover:bg-red-50 transition-colors"
                    title="Delete template"
                  >
                    <span className="material-symbols-outlined text-base">delete</span>
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
