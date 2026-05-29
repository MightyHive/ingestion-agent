"use client"

import { useMemo, useState } from "react"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import { getReportEndpoints } from "@/lib/platforms/registry"
import {
  buildPreviewTableName,
  fieldRowToSchemaColumn,
  type SchemaColumnRow,
} from "@/lib/template-schema"
import TemplateSchemaTable from "@/components/data-connection/TemplateSchemaTable"
import PlatformLogo from "@/components/platforms/PlatformLogo"
import { cn } from "@/lib/utils"

function platformLabel(connectorId: string | null): string {
  if (connectorId === "meta") return "Meta Ads"
  if (connectorId === "tiktok") return "TikTok Ads"
  if (connectorId === "youtube") return "YouTube"
  if (connectorId === "google_ads") return "Google Ads"
  if (connectorId === "dv360") return "Display & Video 360"
  return "—"
}

function resolveScopeLabel(
  endpoints: readonly { id: string; label: string }[],
  id: string | null
): string {
  if (!id) return "—"
  return endpoints.find((e) => e.id === id)?.label ?? id
}

interface ExplorationPreviewPanelProps {
  reportingLevel: string | null
  selectedColumns: string[]
  defaultExpanded?: boolean
}

export default function ExplorationPreviewPanel({
  reportingLevel,
  selectedColumns,
  defaultExpanded = false,
}: ExplorationPreviewPanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const { connectorId, connectorName, fields, templateProposal } = useConnectorStore()

  const endpoints = useMemo(() => getReportEndpoints(connectorId ?? "meta"), [connectorId])
  const scopeLabel = resolveScopeLabel(endpoints, reportingLevel)
  const platform = platformLabel(connectorId)

  const schemaColumns = useMemo((): SchemaColumnRow[] => {
    if (templateProposal && selectedColumns.length > 0) {
      const selectedSet = new Set(selectedColumns)
      const fromProposal = templateProposal.columns.filter((c) =>
        selectedSet.has(c.original)
      )
      if (fromProposal.length > 0) {
        return fromProposal.map((c) => ({
          name: c.name,
          type: c.type,
          mode: c.mode,
        }))
      }
    }

    return selectedColumns.map((id) => {
      const field = fields.find((f) => f.id === id)
      if (field) return fieldRowToSchemaColumn(field)
      return {
        name: id.replace(/\./g, "_").replace(/-/g, "_"),
        type: "STRING",
        mode: "NULLABLE" as const,
      }
    })
  }, [selectedColumns, fields, templateProposal])

  const tableName = templateProposal?.tableName ?? buildPreviewTableName(connectorId, reportingLevel)
  const previewReady = Boolean(connectorId && reportingLevel && selectedColumns.length > 0)

  return (
    <aside
      className={cn(
        "flex flex-col bg-card rounded-2xl border border-border sticky top-24 min-h-0",
        expanded ? "lg:max-h-[calc(100vh-6rem)]" : "h-fit"
      )}
    >
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3 shrink-0">
        <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
          Live preview
        </p>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1 rounded-lg border border-border px-2.5 py-1 text-xs font-medium text-on-surface hover:bg-muted/50 transition-colors"
          aria-expanded={expanded}
        >
          <span className="material-symbols-outlined text-base leading-none">
            {expanded ? "close_fullscreen" : "open_in_full"}
          </span>
          {expanded ? "Compact view" : "Expand preview"}
        </button>
      </div>

      <div className="flex flex-col gap-3 p-4 min-h-0 flex-1 overflow-hidden">
        <div className="grid grid-cols-2 gap-x-3 gap-y-2 text-xs shrink-0">
          <div className="col-span-2 flex items-center gap-2 min-w-0">
            {connectorId && <PlatformLogo platform={connectorId} size="sm" />}
            <MetaItem label="Connector" value={connectorName ?? "—"} className="flex-1" />
          </div>
          <MetaItem label="Platform" value={platform} />
          <MetaItem label="Scope" value={scopeLabel} />
          <MetaItem
            label="Columns"
            value={selectedColumns.length > 0 ? String(selectedColumns.length) : "—"}
          />
        </div>

        <div className="rounded-xl border border-border bg-muted/20 flex flex-col min-h-0 flex-1 overflow-hidden">
          <div className="flex items-start justify-between gap-2 px-3 py-2.5 border-b border-border/80 shrink-0">
            <div className="min-w-0">
              <p className="text-[10px] font-semibold text-on-surface-variant uppercase tracking-wider">
                Template structure
              </p>
              <div className="flex items-center gap-1.5 mt-0.5 min-w-0">
                <span className="material-symbols-outlined text-on-surface-variant text-sm shrink-0">
                  table_chart
                </span>
                <code className="text-xs font-mono font-semibold text-primary truncate">
                  {tableName}
                </code>
              </div>
              <p className="text-[10px] text-on-surface-variant mt-0.5">
                {schemaColumns.length} columns · BigQuery
              </p>
            </div>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium shrink-0">
              Preview
            </span>
          </div>

          <TemplateSchemaTable
            columns={schemaColumns}
            compact
            className={cn(
              "flex-1 min-h-0",
              expanded ? "max-h-[min(70vh,520px)]" : "max-h-[220px]"
            )}
          />
        </div>

        {previewReady ? (
          <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 text-xs text-emerald-800 shrink-0">
            Ready to save as template.
          </div>
        ) : (
          <div className="rounded-lg bg-muted/50 border border-border px-3 py-2 text-xs text-on-surface-variant shrink-0">
            {!connectorId
              ? "Select a connector first."
              : !reportingLevel
                ? "Choose a reporting scope."
                : "Select at least one field to preview columns."}
          </div>
        )}
      </div>
    </aside>
  )
}

function MetaItem({
  label,
  value,
  className,
}: {
  label: string
  value: string
  className?: string
}) {
  return (
    <div className={cn("min-w-0", className)}>
      <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">{label}</p>
      <p className="text-xs font-medium text-on-surface truncate mt-0.5" title={value}>
        {value}
      </p>
    </div>
  )
}
