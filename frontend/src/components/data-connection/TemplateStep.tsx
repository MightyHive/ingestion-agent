"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { useShallow } from "zustand/react/shallow"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import type { TemplateProposal } from "@/lib/stores/connectorStore"
import { useTemplateStore } from "@/lib/stores/templateStore"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Button } from "@/components/ui/button"

export default function TemplateStep({
  data,
  onUpdate: _onUpdate,
}: {
  data: {
    step1?: { platform?: string }
    step2?: { columns?: string[]; reportingLevel?: string | null }
  }
  onUpdate?: (d: Record<string, unknown>) => void
}) {
  void _onUpdate
  const platform = data.step1?.platform
  const columns = data.step2?.columns ?? []
  const reportingLevel = data.step2?.reportingLevel ?? null
  const router = useRouter()
  const {
    connectorId,
    manifest,
    templateProposal,
    isProposing,
    proposalError,
    connectorName,
    clearRunAndProposalErrors,
    setSelectedFields,
    proposeTemplateFromSelection,
  } = useConnectorStore(
    useShallow((s) => ({
      connectorId: s.connectorId,
      manifest: s.manifest,
      templateProposal: s.templateProposal,
      isProposing: s.isProposing,
      proposalError: s.proposalError,
      connectorName: s.connectorName,
      clearRunAndProposalErrors: s.clearRunAndProposalErrors,
      setSelectedFields: s.setSelectedFields,
      proposeTemplateFromSelection: s.proposeTemplateFromSelection,
    }))
  )
  const { addTemplate } = useTemplateStore()

  const [saved, setSaved] = useState(false)
  const [templateName, setTemplateName] = useState("")

  const columnsKey = useMemo(() => [...columns].sort().join("|"), [columns])
  const loading = isProposing
  const buildError = proposalError

  useEffect(() => {
    if (templateProposal?.tableName) {
      setTemplateName(templateProposal.tableName)
    }
  }, [templateProposal?.tableName])

  useEffect(() => {
    if (columns.length === 0) return
    const s = useConnectorStore.getState()
    if (!s.connectorId) return
    if (s.isProposing) return
    if (s.proposalError) return
    s.setSelectedFields(columns)
    s.proposeTemplateFromSelection(reportingLevel)
  }, [columnsKey, connectorId, reportingLevel])

  const handleRetry = useCallback(() => {
    clearRunAndProposalErrors()
    setSelectedFields(columns)
    proposeTemplateFromSelection(reportingLevel)
  }, [clearRunAndProposalErrors, setSelectedFields, proposeTemplateFromSelection, columns, reportingLevel])

  const handleApprove = useCallback(() => {
    if (!templateProposal) return
    const name = templateName.trim() || templateProposal.tableName
    addTemplate({
      tableName: name,
      manifestId: manifest?.id ?? connectorId ?? undefined,
      platform: manifest?.platform ?? platform ?? "",
      endpoint: reportingLevel ?? "all",
      columns: templateProposal.columns,
      ddl: templateProposal.ddl,
    })
    setSaved(true)
  }, [addTemplate, platform, manifest, connectorId, templateName, templateProposal, reportingLevel])

  if (!loading && !templateProposal && !buildError && columns.length === 0) {
    return (
      <EmptyState
        icon="template"
        title="There is no template yet."
        hint="Select at least one field in the previous step."
        onBack={() => router.push("/data-connection")}
      />
    )
  }

  if (!loading && !templateProposal && !buildError && columns.length > 0 && !connectorId) {
    return (
      <EmptyState
        icon="link_off"
        title="No connector is active."
        hint="Go back and choose a connector."
        onBack={() => router.push("/data-connection")}
      />
    )
  }

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">Template</h1>
        <p className="text-sm text-on-surface-variant mt-0.5">
          Review the extraction template from your field selection. Data is fetched later in Export Planner.
        </p>
      </div>

      {buildError && (
        <div className="bg-card rounded-2xl border border-red-200 p-6 flex flex-col gap-3 text-red-700">
          <ErrorPanel error={buildError} onRetry={handleRetry} onBack={() => router.push("/data-connection")} />
        </div>
      )}

      {loading && !templateProposal && (
        <LoadingCard />
      )}

      {templateProposal && (
        <TemplateContent
          proposal={templateProposal}
          connectorName={connectorName}
          columnsCount={columns.length}
          reportingLevel={reportingLevel}
          templateName={templateName}
          setTemplateName={setTemplateName}
          saved={saved}
          onApprove={handleApprove}
          onGoExport={() => router.push("/data-export")}
        />
      )}
    </div>
  )
}

function EmptyState({
  icon,
  title,
  hint,
  onBack,
}: {
  icon: string
  title: string
  hint: string
  onBack: () => void
}) {
  return (
    <div className="space-y-6 max-w-[1200px]">
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <span className="material-symbols-outlined text-4xl text-on-surface-variant">{icon}</span>
        <p className="text-sm text-on-surface-variant">{title}</p>
        <p className="text-xs text-on-surface-variant">{hint}</p>
        <button
          type="button"
          onClick={onBack}
          className="text-sm font-semibold text-primary hover:underline"
        >
          Back to data connection
        </button>
      </div>
    </div>
  )
}

function ErrorPanel({
  error,
  onRetry,
  onBack,
}: {
  error: string
  onRetry: () => void
  onBack: () => void
}) {
  return (
    <>
      <div className="flex items-start gap-3">
        <span className="material-symbols-outlined shrink-0">error</span>
        <ErrorText error={error} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onBack}>
          Back to data connection
        </Button>
      </div>
    </>
  )
}

function ErrorText({ error }: { error: string }) {
  return (
    <div className="min-w-0 flex-1">
      <p className="font-semibold text-sm">Could not build template</p>
      <p className="text-xs mt-1 break-words">{error}</p>
    </div>
  )
}

function LoadingCard() {
  return (
    <div className="bg-card rounded-2xl border border-border p-10 flex flex-col items-center justify-center gap-3 text-on-surface-variant">
      <span
        className="material-symbols-outlined text-3xl animate-spin"
        style={{ animationDuration: "1.2s" }}
        aria-hidden
      >
        progress_activity
      </span>
      <p className="text-sm font-medium text-on-surface">Building template…</p>
    </div>
  )
}

function TemplateContent({
  proposal,
  connectorName,
  columnsCount,
  reportingLevel,
  templateName,
  setTemplateName,
  saved,
  onApprove,
  onGoExport,
}: {
  proposal: TemplateProposal
  connectorName: string | null
  columnsCount: number
  reportingLevel: string | null
  templateName: string
  setTemplateName: (v: string) => void
  saved: boolean
  onApprove: () => void
  onGoExport: () => void
}) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">
      <FieldMappingCard proposal={proposal} />

      <div className="flex flex-col gap-4">
        <div className="bg-card rounded-2xl border border-border p-5 flex flex-col gap-3">
          <MetaRow label="Connector" value={connectorName ?? "—"} />
          <MetaRow label="Selected fields" value={String(columnsCount)} />
          {reportingLevel ? <MetaRow label="Reporting scope" value={reportingLevel} /> : null}
          <SuggestedTableRow name={proposal.tableName} />
        </div>

        <div className="bg-card rounded-2xl border border-border p-5">
          <div className="flex items-start gap-2 mb-2">
            <span className="material-symbols-outlined text-primary text-base mt-0.5">info</span>
            <p className="text-xs font-semibold text-on-surface">What happens next</p>
          </div>
          <p className="text-xs text-on-surface-variant leading-relaxed">
            This step defines which fields belong in your template. Ingestion and warehouse load run from Export
            Planner when you schedule or backfill.
          </p>
        </div>

        {!saved && (
          <div className="bg-card rounded-2xl border border-border p-5 flex flex-col gap-2">
            <Label
              htmlFor="template-save-name"
              className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider"
            >
              Template name
            </Label>
            <Input
              id="template-save-name"
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              className="font-mono text-sm"
              placeholder="Name for this template"
            />
            <p className="text-xs text-on-surface-variant">
              Save to reuse in Export Planner when you schedule or run ingestion.
            </p>
          </div>
        )}

        {saved ? (
          <SavedBlock name={templateName.trim() || proposal.tableName} onGoExport={onGoExport} />
        ) : (
          <button
            type="button"
            onClick={onApprove}
            className="w-full py-2.5 px-4 bg-primary text-white rounded-xl font-semibold text-sm hover:bg-primary/90 transition-colors flex items-center justify-center gap-2"
          >
            <span className="material-symbols-outlined text-base">save</span>
            Save template
          </button>
        )}
      </div>
    </div>
  )
}

function SuggestedTableRow({ name }: { name: string }) {
  return (
    <div>
      <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-1">Suggested table</p>
      <code className="text-xs font-mono text-primary">{name}</code>
    </div>
  )
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-1">{label}</p>
      <p className="text-sm font-semibold text-on-surface">{value}</p>
    </div>
  )
}

function FieldMappingCard({ proposal }: { proposal: TemplateProposal }) {
  return (
    <div className="bg-card rounded-2xl border border-border p-5 flex flex-col gap-4">
      <div>
        <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-1">Field mapping</p>
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-on-surface-variant text-base">table_chart</span>
          <code className="text-sm font-mono font-semibold text-primary">{proposal.tableName}</code>
        </div>
        <p className="text-xs text-on-surface-variant mt-1">
          {proposal.columns.length} column{proposal.columns.length === 1 ? "" : "s"} in this template
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
                Source field
              </th>
              <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
                Column
              </th>
              <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
                Type
              </th>
              <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
                Mode
              </th>
              <th className="text-left py-2 px-2 text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
                Description
              </th>
            </tr>
          </thead>
          <tbody>
            {proposal.columns.map((col) => (
              <tr key={col.original} className="border-b border-border/50 hover:bg-muted/30 transition-colors">
                <td className="py-2 px-2">
                  <span className="text-xs text-on-surface-variant">{col.original}</span>
                </td>
                <td className="py-2 px-2">
                  <span className="text-xs text-on-surface-variant">{col.name}</span>
                </td>
                <td className="py-2 px-2">
                  <span className="text-xs text-on-surface-variant">{col.type}</span>
                </td>
                <td className="py-2 px-2">
                  <span className="text-xs text-on-surface-variant">{col.mode}</span>
                </td>
                <td className="py-2 px-2 max-w-xs">
                  <span className="text-xs text-on-surface-variant">{col.description ?? "—"}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function SavedBlock({ name, onGoExport }: { name: string; onGoExport: () => void }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="w-full py-3 px-4 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center gap-2 text-emerald-800 text-sm font-semibold">
        <span className="material-symbols-outlined text-base">check_circle</span>
        Template saved
      </div>
      <p className="text-xs text-on-surface-variant text-center">
        <code className="font-mono">{name}</code> is ready to use.
      </p>
      <button
        type="button"
        onClick={onGoExport}
        className="w-full py-2.5 px-4 bg-primary text-white rounded-xl font-semibold text-sm hover:bg-primary/90 transition-colors flex items-center justify-center gap-2"
      >
        <span className="material-symbols-outlined text-base">upload</span>
        Go to Data Export
      </button>
    </div>
  )
}
