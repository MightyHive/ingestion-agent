"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"

export interface Column {
  id: string
  name: string
  type: "STRING" | "INTEGER" | "FLOAT" | "DATE" | "BOOLEAN"
  category: "performance" | "conversion" | "structural" | string
  description?: string
}

interface ColumnSelectorProps {
  message: string
  columns: Column[]
  onConfirm: (selected: string[]) => void
  isLoading?: boolean
}

const TYPE_COLORS: Record<string, string> = {
  STRING:  "bg-blue-50 text-blue-700",
  INTEGER: "bg-purple-50 text-purple-700",
  FLOAT:   "bg-amber-50 text-amber-700",
  DATE:    "bg-green-50 text-green-700",
  BOOLEAN: "bg-slate-100 text-slate-600",
}

const CATEGORIES = [
  { id: "all",         label: "All" },
  { id: "performance", label: "Performance" },
  { id: "conversion",  label: "Conversion" },
  { id: "structural",  label: "Structural" },
]

const CATEGORY_ACCENT: Record<string, string> = {
  performance: "text-blue-700 bg-blue-50 border-blue-200",
  conversion:  "text-purple-700 bg-purple-50 border-purple-200",
  structural:  "text-slate-600 bg-slate-100 border-slate-200",
}

export default function ColumnSelector({
  message,
  columns,
  onConfirm,
  isLoading = false,
}: ColumnSelectorProps) {
  const [selected, setSelected]     = useState<Set<string>>(new Set())
  const [search, setSearch]         = useState("")
  const [activeTab, setActiveTab]   = useState("all")

  // Filtrar por búsqueda y categoría activa
  const filtered = columns.filter((c) => {
    const matchesSearch = c.name.toLowerCase().includes(search.toLowerCase()) ||
                          c.id.toLowerCase().includes(search.toLowerCase())
    const matchesTab    = activeTab === "all" || c.category === activeTab
    return matchesSearch && matchesTab
  })

  // Contadores por categoría
  const countByCategory = (cat: string) =>
    cat === "all" ? columns.length : columns.filter(c => c.category === cat).length

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  function toggleCategory() {
    // Selecciona/deselecciona solo los de la tab activa
    const inTab = filtered.map(c => c.id)
    const allSelected = inTab.every(id => selected.has(id))
    setSelected((prev) => {
      const next = new Set(prev)
      if (allSelected) {
        inTab.forEach(id => next.delete(id))
      } else {
        inTab.forEach(id => next.add(id))
      }
      return next
    })
  }

  const inTabAllSelected = filtered.length > 0 && filtered.every(c => selected.has(c.id))

  return (
    <div className="flex flex-col gap-4">

      {/* Tabs de categoría */}
      <div className="flex gap-1 p-1 bg-muted rounded-xl">
        {CATEGORIES.map((cat) => {
          const count = countByCategory(cat.id)
          return (
            <button
              key={cat.id}
              onClick={() => setActiveTab(cat.id)}
              className={cn(
                "flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
                activeTab === cat.id
                  ? "bg-white text-on-surface shadow-sm"
                  : "text-on-surface-variant hover:text-on-surface"
              )}
            >
              {cat.label}
              <span className={cn(
                "text-[10px] font-bold px-1.5 py-0.5 rounded-full",
                activeTab === cat.id
                  ? cat.id !== "all" ? CATEGORY_ACCENT[cat.id] : "bg-primary/10 text-primary"
                  : "bg-transparent text-on-surface-variant"
              )}>
                {count}
              </span>
            </button>
          )
        })}
      </div>

      {/* Search + select category */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-on-surface-variant text-base">
            search
          </span>
          <input
            type="text"
            placeholder="Search fields..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 h-8 text-sm border border-border rounded-lg bg-background outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 placeholder:text-on-surface-variant"
          />
        </div>
        <button
          onClick={toggleCategory}
          className="text-xs font-semibold text-primary hover:underline flex-shrink-0 whitespace-nowrap"
        >
          {inTabAllSelected ? "Deselect all" : "Select all"}
        </button>
      </div>

      {/* Contador global */}
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

      {/* Lista de campos */}
      <div className="flex flex-col gap-1.5 max-h-72 overflow-y-auto pr-1">
        {filtered.length === 0 && (
          <p className="text-sm text-on-surface-variant text-center py-6">
            No fields match your search.
          </p>
        )}
        {filtered.map((col) => {
          const isSelected = selected.has(col.id)
          return (
            <button
              key={col.id}
              onClick={() => toggle(col.id)}
              className={cn(
                "flex items-center gap-3 p-3 rounded-xl border text-left transition-all",
                isSelected
                  ? "border-primary/40 bg-primary/5"
                  : "border-border bg-background hover:bg-muted/50"
              )}
            >
              {/* Checkbox */}
              <div className={cn(
                "w-4 h-4 rounded flex-shrink-0 border-2 flex items-center justify-center transition-colors",
                isSelected ? "bg-primary border-primary" : "border-border bg-white"
              )}>
                {isSelected && (
                  <svg viewBox="0 0 10 8" className="w-2.5 h-2.5">
                    <path d="M1 4l2.5 2.5L9 1" stroke="white" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </div>

              <span className="flex-1 text-sm font-medium text-on-surface">
                {col.name}
              </span>

              {/* Tipo */}
              <span className={cn(
                "text-xs font-semibold px-2 py-0.5 rounded flex-shrink-0",
                TYPE_COLORS[col.type] ?? "bg-slate-100 text-slate-600"
              )}>
                {col.type}
              </span>
            </button>
          )
        })}
      </div>

      {/* Confirm */}
      <button
        disabled={selected.size === 0 || isLoading}
        onClick={() => onConfirm(Array.from(selected))}
        className="w-full py-2.5 px-4 bg-primary text-white rounded-xl font-semibold text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-primary/90 transition-colors"
      >
        {isLoading
          ? "Processing..."
          : selected.size === 0
          ? "Select at least one field"
          : `Confirm ${selected.size} field${selected.size !== 1 ? "s" : ""}`}
      </button>
    </div>
  )
}