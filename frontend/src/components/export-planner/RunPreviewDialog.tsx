"use client"

import { useMemo } from "react"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import type { TemplateRunResult } from "@/lib/export-ingestion"

function cellText(value: unknown): string {
  if (value === null || value === undefined) return "—"
  if (typeof value === "object") return JSON.stringify(value)
  return String(value)
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
  result: TemplateRunResult | null
  templateName: string
}

export default function RunPreviewDialog({ open, onOpenChange, result, templateName }: Props) {
  const columns = useMemo(() => {
    if (!result) return []
    if (result.columns.length > 0) return result.columns
    const first = result.rows_preview[0]
    if (first && typeof first === "object") return Object.keys(first)
    return []
  }, [result])

  function downloadJson() {
    if (!result) return
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `run-preview-${templateName.replace(/\W+/g, "_")}-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (!result) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-4xl max-h-[85vh] flex flex-col bg-white">
        <DialogHeader>
          <DialogTitle>Run preview</DialogTitle>
          <p className="text-sm text-muted-foreground">
            {result.row_count.toLocaleString()} rows reported · showing {result.rows_preview.length} sample
            row{result.rows_preview.length === 1 ? "" : "s"} (not loaded to BigQuery yet).
          </p>
        </DialogHeader>

        <PreviewTable columns={columns} rows={result.rows_preview} />

        <DialogFooter className="gap-2 sm:gap-0">
          <Button type="button" variant="outline" onClick={downloadJson}>
            Download JSON
          </Button>
          <Button type="button" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function PreviewTable({
  columns,
  rows,
}: {
  columns: string[]
  rows: Record<string, unknown>[]
}) {
  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-6 text-center">
        No sample rows in the API response. Check the terminal or Network tab for the full payload.
      </p>
    )
  }

  return (
    <div className="overflow-auto flex-1 min-h-0 rounded-xl border max-h-[50vh]">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-muted/90 backdrop-blur-sm z-[1]">
          <tr>
            {columns.map((c) => (
              <th
                key={c}
                className="text-left py-2 px-2 font-semibold text-muted-foreground whitespace-nowrap border-b"
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-border/50 hover:bg-muted/20">
              {columns.map((c) => (
                <td
                  key={c}
                  className="py-1.5 px-2 font-mono max-w-[200px] truncate"
                  title={cellText(row[c])}
                >
                  {cellText(row[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
