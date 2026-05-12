"use client"

import { cn } from "@/lib/utils"
import { useDestinationStore } from "@/lib/stores/destinationStore"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { SavedDestination } from "@/lib/stores/destinationStore"

export type DestinationsSelectData = {
  projectId: string
  serviceAccountEmail: string
  destinationKind: "bigquery" | "gcs"
  bigQueryDataset: string
  gcsBucket: string
  gcsPrefix: string
}

export type DestinationsStepProps =
  | { variant: "browse" }
  | {
      variant?: "select"
      data: DestinationsSelectData
      onUpdate: (data: Record<string, unknown>) => void
    }

function ConnectionsTable({
  rows,
  onDelete,
}: {
  rows: SavedDestination[]
  onDelete: (id: string) => void
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Project</TableHead>
          <TableHead className="font-mono text-xs">ID</TableHead>
          <TableHead className="font-mono text-xs">Region</TableHead>
          <TableHead>Service account</TableHead>
          <TableHead className="w-14 text-right" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((project) => (
          <TableRow key={project.id}>
            <TableCell>
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-[#4285F4] flex items-center justify-center flex-shrink-0">
                  <span className="material-symbols-outlined text-white text-sm">cloud</span>
                </div>
                <span className="text-sm font-medium text-on-surface">{project.name}</span>
              </div>
            </TableCell>
            <TableCell className="text-xs text-muted-foreground font-mono align-middle">
              {project.projectId}
            </TableCell>
            <TableCell className="text-xs font-mono align-middle">{project.region}</TableCell>
            <TableCell className="text-xs font-mono break-all max-w-[280px] text-on-surface">
              {project.serviceAccount}
            </TableCell>
            <TableCell className="text-right">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="text-destructive hover:text-destructive h-8 w-8"
                onClick={() => onDelete(project.id)}
                aria-label="Delete connection"
              >
                <span className="material-symbols-outlined text-base">delete</span>
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

export default function DestinationsStep(props: DestinationsStepProps) {
  const destinations = useDestinationStore((s) => s.destinations)
  const deleteDestination = useDestinationStore((s) => s.deleteDestination)

  if (props.variant === "browse") {
    return (
      <div className="max-w-[1200px]">
        <ConnectionsTable rows={destinations} onDelete={deleteDestination} />
      </div>
    )
  }

  const { data, onUpdate } = props
  const selected = destinations.find((p) => p.projectId === data.projectId) ?? null

  function handleSelect(d: SavedDestination) {
    onUpdate({ projectId: d.projectId, serviceAccountEmail: d.serviceAccount })
  }

  const isBigQuery = data.destinationKind === "bigquery"

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">Destinations</h1>
        <p className="text-sm text-on-surface-variant mt-0.5">
          Select the GCP project where data will be loaded, then choose BigQuery or Cloud Storage as the load target.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {destinations.map((project) => {
          const isSelected = data.projectId === project.projectId
          return (
            <button
              key={project.id}
              type="button"
              onClick={() => handleSelect(project)}
              className={cn(
                "bg-card rounded-2xl border p-5 flex flex-col gap-3 shadow-sm text-left transition-all",
                isSelected
                  ? "border-primary/50 ring-2 ring-primary/20 bg-primary/5"
                  : "border-border hover:border-primary/30"
              )}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-[#4285F4] flex items-center justify-center flex-shrink-0">
                    <span className="material-symbols-outlined text-white text-base">cloud</span>
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-on-surface">{project.name}</p>
                    <p className="text-xs text-on-surface-variant font-mono">{project.projectId}</p>
                  </div>
                </div>
                {isSelected && (
                  <span className="material-symbols-outlined text-primary text-base">check_circle</span>
                )}
              </div>

              <div className="flex flex-col gap-1">
                <p className="text-xs text-on-surface-variant uppercase tracking-wider font-semibold">Region</p>
                <p className="text-xs font-mono text-on-surface">{project.region}</p>
              </div>

              <div className="flex flex-col gap-1">
                <p className="text-xs text-on-surface-variant uppercase tracking-wider font-semibold">Service Account</p>
                <p className="text-xs font-mono text-on-surface break-all">{project.serviceAccount}</p>
              </div>
            </button>
          )
        })}
      </div>

      <section
        className={cn(
          "rounded-2xl border border-border bg-card p-5 flex flex-col gap-4 transition-opacity",
          !data.projectId && "pointer-events-none opacity-40"
        )}
      >
        <div>
          <h2 className="text-sm font-semibold text-on-surface uppercase tracking-wider">Load target</h2>
          <p className="text-xs text-on-surface-variant mt-1">
            {data.projectId
              ? "Choose whether exports land in BigQuery (DDL preview) or as objects in GCS."
              : "Select a GCP project above to configure the load target."}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!data.projectId}
            onClick={() => onUpdate({ destinationKind: "bigquery" })}
            className={cn(
              "px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors",
              isBigQuery
                ? "bg-primary text-white border-primary"
                : "bg-background text-on-surface border-border hover:border-primary/40"
            )}
          >
            BigQuery
          </button>
          <button
            type="button"
            disabled={!data.projectId}
            onClick={() => onUpdate({ destinationKind: "gcs" })}
            className={cn(
              "px-3 py-1.5 rounded-lg text-xs font-semibold border transition-colors",
              !isBigQuery
                ? "bg-primary text-white border-primary"
                : "bg-background text-on-surface border-border hover:border-primary/40"
            )}
          >
            Cloud Storage
          </button>
        </div>

        {isBigQuery ? (
          <div className="flex flex-col gap-1.5 max-w-md">
            <label className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
              Dataset ID
            </label>
            <input
              type="text"
              disabled={!data.projectId}
              value={data.bigQueryDataset}
              onChange={(e) => onUpdate({ bigQueryDataset: e.target.value })}
              className="font-mono text-sm px-3 py-2 border border-border rounded-lg bg-background outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
              placeholder="e.g. bronze_ads"
            />
          </div>
        ) : (
          <div className="grid gap-4 max-w-lg sm:grid-cols-2">
            <div className="flex flex-col gap-1.5 sm:col-span-2">
              <label className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
                Bucket
              </label>
              <input
                type="text"
                disabled={!data.projectId}
                value={data.gcsBucket}
                onChange={(e) => onUpdate({ gcsBucket: e.target.value })}
                className="font-mono text-sm px-3 py-2 border border-border rounded-lg bg-background outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                placeholder="my-export-bucket or gs://my-export-bucket"
              />
            </div>
            <div className="flex flex-col gap-1.5 sm:col-span-2">
              <label className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
                Prefix (optional)
              </label>
              <input
                type="text"
                disabled={!data.projectId}
                value={data.gcsPrefix}
                onChange={(e) => onUpdate({ gcsPrefix: e.target.value })}
                className="font-mono text-sm px-3 py-2 border border-border rounded-lg bg-background outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                placeholder="exports/meta/daily"
              />
            </div>
          </div>
        )}
      </section>

      {selected && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm">
          <span className="material-symbols-outlined text-base">check_circle</span>
          <span>
            Project <strong>{selected.name}</strong> selected · SA will connect as{" "}
            <code className="text-xs font-mono">{selected.serviceAccount}</code>
          </span>
        </div>
      )}
    </div>
  )
}
