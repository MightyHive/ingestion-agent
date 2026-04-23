"use client"

import { cn } from "@/lib/utils"

const MOCK_GCP_PROJECTS = [
  { id: "mds-prod-421",     name: "MDS Production",     sa: "mds-agent@mds-prod-421.iam.gserviceaccount.com",     region: "us-east1" },
  { id: "cadillac-gcp-01",  name: "Cadillac Analytics",  sa: "mds-agent@cadillac-gcp-01.iam.gserviceaccount.com",  region: "eu-west1" },
  { id: "renault-bq-prod",  name: "Renault Analytics",   sa: "mds-agent@renault-bq-prod.iam.gserviceaccount.com",  region: "eu-west1" },
]

interface Props {
  data: { projectId: string; serviceAccountEmail: string }
  onUpdate: (data: Record<string, unknown>) => void
}

export default function DestinationsStep({ data, onUpdate }: Props) {
  const selected = MOCK_GCP_PROJECTS.find((p) => p.id === data.projectId) ?? null

  function handleSelect(project: typeof MOCK_GCP_PROJECTS[number]) {
    onUpdate({ projectId: project.id, serviceAccountEmail: project.sa })
  }

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">Destinations</h1>
        <p className="text-sm text-on-surface-variant mt-0.5">
          Select the GCP project where data will be loaded. A service account will be associated automatically.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {MOCK_GCP_PROJECTS.map((project) => {
          const isSelected = data.projectId === project.id
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
                    <p className="text-xs text-on-surface-variant font-mono">{project.id}</p>
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
                <p className="text-xs font-mono text-on-surface break-all">{project.sa}</p>
              </div>

              <div className="flex items-center gap-1.5 mt-auto">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                <span className="text-xs text-emerald-700 font-medium">BigQuery Editor</span>
              </div>
            </button>
          )
        })}
      </div>

      {selected && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm">
          <span className="material-symbols-outlined text-base">check_circle</span>
          <span>
            Project <strong>{selected.name}</strong> selected · SA will connect as{" "}
            <code className="text-xs font-mono">{selected.sa}</code>
          </span>
        </div>
      )}

      <div className="border-t border-border pt-4">
        <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-2">Coming soon</p>
        <p className="text-xs text-on-surface-variant">
          Google OAuth login will replace mock projects with your real GCP organization and allow linking custom service accounts.
        </p>
      </div>
    </div>
  )
}
