"use client"

import Link from "next/link"
import { onboardingSteps } from "@/lib/mock-data"
import { useCredentialStore } from "@/lib/stores/credentialStore"
import { useTemplateStore } from "@/lib/stores/templateStore"
import { useExportJobStore } from "@/lib/stores/exportJobStore"

const STEP_DONE: Record<string, (ctx: { hasCredentials: boolean; hasTemplates: boolean; hasJobs: boolean }) => boolean> = {
  connector: ({ hasCredentials }) => hasCredentials,
  selector: ({ hasTemplates }) => hasTemplates,
  schema: ({ hasTemplates }) => hasTemplates,
  scheduler: ({ hasJobs }) => hasJobs,
}

export default function OnboardingGuide({ compact = false }: { compact?: boolean }) {
  const credentials = useCredentialStore((s) => s.credentials)
  const templates = useTemplateStore((s) => s.templates)
  const jobs = useExportJobStore((s) => s.jobs)

  const ctx = {
    hasCredentials: credentials.length > 0,
    hasTemplates: templates.length > 0,
    hasJobs: jobs.length > 0,
  }

  const completedCount = onboardingSteps.filter((step) => STEP_DONE[step.id]?.(ctx)).length
  const allDone = completedCount === onboardingSteps.length

  return (
    <div className="bg-card rounded-2xl border border-border p-6 flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-primary text-2xl">rocket_launch</span>
          <div>
            <h2 className="font-semibold text-on-surface">
              {allDone ? "Setup complete" : "Start connecting your data"}
            </h2>
            <p className="text-sm text-on-surface-variant">
              {allDone
                ? "All onboarding steps are done. You can revisit any step below."
                : "Follow these steps to create your first pipeline"}
            </p>
          </div>
        </div>
        <span className="text-xs font-semibold text-on-surface-variant whitespace-nowrap">
          {completedCount}/{onboardingSteps.length} complete
        </span>
      </div>

      <div className={`grid gap-3 ${compact ? "grid-cols-2 lg:grid-cols-4" : "grid-cols-2 sm:grid-cols-4"}`}>
        {onboardingSteps.map((step, i) => {
          const done = STEP_DONE[step.id]?.(ctx) ?? false
          return (
            <Link
              key={step.id}
              href={step.href}
              className={`flex flex-col gap-2 p-4 rounded-xl border transition-all ${
                done
                  ? "border-emerald-200 bg-emerald-50/50 hover:border-emerald-300"
                  : "border-border hover:border-primary/40 hover:bg-primary/5"
              }`}
            >
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                  done ? "bg-emerald-500 text-white" : "bg-muted text-on-surface-variant"
                }`}
              >
                {done ? "✓" : i + 1}
              </div>
              <span className="text-sm font-medium text-on-surface">{step.label}</span>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
