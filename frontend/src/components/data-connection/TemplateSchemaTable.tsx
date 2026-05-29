"use client"

import { cn } from "@/lib/utils"
import type { SchemaColumnRow } from "@/lib/template-schema"

interface TemplateSchemaTableProps {
  columns: SchemaColumnRow[]
  showDescription?: boolean
  compact?: boolean
  className?: string
}

export default function TemplateSchemaTable({
  columns,
  showDescription = false,
  compact = false,
  className,
}: TemplateSchemaTableProps) {
  if (columns.length === 0) {
    return (
      <p className="text-sm text-on-surface-variant py-6 text-center">
        Select fields to preview the template structure.
      </p>
    )
  }

  const cellPad = compact ? "py-1.5 px-2" : "py-2 px-2"
  const textSize = compact ? "text-[11px]" : "text-xs"

  return (
    <div className={cn("overflow-x-auto overflow-y-auto", className)}>
      <table className="w-full min-w-[280px] text-sm">
        <thead className="sticky top-0 bg-card z-10">
          <tr className="border-b border-border">
            <th
              className={cn(
                "text-left font-semibold text-on-surface-variant uppercase tracking-wider",
                cellPad,
                textSize
              )}
            >
              Field
            </th>
            <th
              className={cn(
                "text-left font-semibold text-on-surface-variant uppercase tracking-wider",
                cellPad,
                textSize
              )}
            >
              Type
            </th>
            <th
              className={cn(
                "text-left font-semibold text-on-surface-variant uppercase tracking-wider",
                cellPad,
                textSize
              )}
            >
              Mode
            </th>
            {showDescription && (
              <th
                className={cn(
                  "text-left font-semibold text-on-surface-variant uppercase tracking-wider min-w-[120px]",
                  cellPad,
                  textSize
                )}
              >
                Description
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {columns.map((col) => (
            <tr
              key={col.name}
              className="border-b border-border/50 hover:bg-muted/30 transition-colors"
            >
              <td className={cellPad}>
                <code className={cn("font-mono text-on-surface", textSize)}>{col.name}</code>
              </td>
              <td className={cellPad}>
                <code className={cn("font-mono text-on-surface-variant", textSize)}>{col.type}</code>
              </td>
              <td className={cellPad}>
                <code className={cn("font-mono text-on-surface-variant", textSize)}>{col.mode}</code>
              </td>
              {showDescription && (
                <td className={cellPad}>
                  <span className={cn("text-on-surface-variant", textSize)}>
                    {col.description?.trim() ? col.description.trim() : "—"}
                  </span>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
