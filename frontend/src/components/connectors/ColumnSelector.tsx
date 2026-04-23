"use client"

import { useEffect, useRef, useState } from "react"
import type { FieldRow, ReportEndpoint } from "@/lib/platforms/types"
import { cn } from "@/lib/utils"

/** @deprecated Prefer importing `FieldRow` from `@/lib/platforms/types`. */
export type Column = FieldRow

interface ColumnSelectorProps {
  message: string
  columns: FieldRow[]
  /** Object-level groups for tabs (e.g. Campaign, Ad set, Ad). "All" is always prepended in the UI. */
  endpointTabs: readonly ReportEndpoint[]
  onSelectionChange: (ids: string[]) => void

}

const TYPE_COLORS: Record<string, string> = {
  STRING:  "bg-blue-50 text-blue-700",
  INTEGER: "bg-purple-50 text-purple-700",
  FLOAT:   "bg-amber-50 text-amber-700",
  DATE:    "bg-green-50 text-green-700",
  BOOLEAN: "bg-slate-100 text-slate-600",
}

const KIND_COLORS: Record<FieldRow["kind"], string> = {
  metric:    "text-emerald-800 bg-emerald-50 border-emerald-200",
  dimension: "text-slate-700 bg-slate-100 border-slate-200",
}

function countForTab(
  colList: readonly FieldRow[],
  tab: string
): number {
  if (tab === "all") return colList.length
  if (tab === "metric") {return colList.filter((c) => c.kind === "metric").length}
  if (tab === "dimension") {return colList.filter((c) => c.kind === "dimension").length}
  return colList.filter((c) => c.kind === "metric" || c.endpoint === tab).length;
}

function isRowInTab(c: FieldRow, tab: string): boolean {
  if (tab === "all") return true
  if (tab === "metric") return c.kind === "metric"
  if (tab === "dimension") return c.kind === "dimension"
  return c.kind === "metric" || c.endpoint === tab
}

export default function ColumnSelector({
  message,
  columns,
  endpointTabs,
  onSelectionChange,
}: ColumnSelectorProps) {
  const onSelectionChangeRef = useRef(onSelectionChange)
  onSelectionChangeRef.current = onSelectionChange

  const withAll: { id: string; label: string }[] = [
    { id: "all", label: "All" },
    ...endpointTabs,
  ]

  const [search, setSearch] = useState("")
  const [activeTab, setActiveTab] = useState("all")
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const lastPayloadRef = useRef<string | null>(null)

  useEffect(() => {
    const ids = [...selected].sort()
    const key = JSON.stringify(ids)
    if (lastPayloadRef.current === key) return
    lastPayloadRef.current = key
    onSelectionChangeRef.current(ids)
  }, [selected])

  const filtered = columns.filter((c) => {
    const matchesSearch =
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.id.toLowerCase().includes(search.toLowerCase())
    return matchesSearch && isRowInTab(c, activeTab)
  })

  const countByTab = (id: string) => countForTab(columns, id)

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleInView() {
    const inTab = filtered.map((c) => c.id)
    const allOn = inTab.length > 0 && inTab.every((id) => selected.has(id))
    setSelected((prev) => {
      const next = new Set(prev)
      if (allOn) inTab.forEach((id) => next.delete(id))
      else inTab.forEach((id) => next.add(id))
      return next
    })
  }

  const inTabAllSelected =
    filtered.length > 0 && filtered.every((c) => selected.has(c.id))

  return (
    <div className="flex flex-col gap-4">
      {message.trim() ? (
        <p className="text-sm text-on-surface leading-relaxed">{message}</p>
      ) : null}

      <div className="flex gap-1 p-1 bg-muted rounded-xl flex-wrap">
        {withAll.map((cat) => {
          const count = countByTab(cat.id)
          return (
            <button
              key={cat.id}
              type="button"
              onClick={() => setActiveTab(cat.id)}
              className={cn(
                "flex-1 min-w-[72px] flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
                activeTab === cat.id
                  ? "bg-white text-on-surface shadow-sm"
                  : "text-on-surface-variant hover:text-on-surface"
              )}
            >
              {cat.label}
              <span
                className={cn(
                  "text-[10px] font-bold px-1.5 py-0.5 rounded-full",
                  activeTab === cat.id
                    ? cat.id === "all"
                      ? "bg-primary/10 text-primary"
                      : "bg-slate-100 text-slate-700"
                    : "bg-transparent text-on-surface-variant"
                )}
              >
                {count}
              </span>
            </button>
          )
        })}
      </div>

      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-on-surface-variant text-base">
            search
          </span>
          <input
            type="text"
            placeholder="Search fields…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 h-8 text-sm border border-border rounded-lg bg-background outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 placeholder:text-on-surface-variant"
          />
        </div>
        <button
          type="button"
          onClick={toggleInView}
          className="text-xs font-semibold text-primary hover:underline flex-shrink-0 whitespace-nowrap"
        >
          {inTabAllSelected ? "Deselect all" : "Select all in view"}
        </button>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-on-surface-variant font-medium">
          {filtered.length} fields
        </span>
        {selected.size > 0 && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-primary text-white font-medium">
            {selected.size} selected
          </span>
        )}
      </div>

      <div className="flex flex-col gap-1.5 max-h-72 overflow-y-auto pr-1">
        {filtered.length === 0 && (
          <p className="text-sm text-on-surface-variant text-center py-6">
            No fields match your search in this view.
          </p>
        )}
        {filtered.map((col) => {
          const isOn = selected.has(col.id)
          return (
            <button
              key={col.id}
              type="button"
              onClick={() => toggle(col.id)}
              className={cn(
                "flex items-center gap-3 p-3 rounded-xl border text-left transition-all",
                isOn
                  ? "border-primary/40 bg-primary/5"
                  : "border-border bg-background hover:bg-muted/50"
              )}
            >
              <div
                className={cn(
                  "w-4 h-4 rounded flex-shrink-0 border-2 flex items-center justify-center transition-colors",
                  isOn ? "bg-primary border-primary" : "border-border bg-white"
                )}
              >
                {isOn && (
                  <svg viewBox="0 0 10 8" className="w-2.5 h-2.5" aria-hidden>
                    <path
                      d="M1 4l2.5 2.5L9 1"
                      stroke="white"
                      strokeWidth="1.5"
                      fill="none"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
              </div>

              <span className="flex-1 text-sm font-medium text-on-surface min-w-0 truncate">
                {col.name}
              </span>

              <span
                className={cn(
                  "text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded border flex-shrink-0",
                  KIND_COLORS[col.kind]
                )}
                title={col.kind === "metric" ? "Metric" : "Dimension"}
              >
                {col.kind === "metric" ? "Metric" : "Dimension"}
              </span>
              <span
                className={cn(
                  "text-xs font-semibold px-2 py-0.5 rounded flex-shrink-0",
                  TYPE_COLORS[col.type] ?? "bg-slate-100 text-slate-600"
                )}
              >
                {col.type}
              </span>
            </button>
          )
        })}
      </div>

    </div>
  )
}
