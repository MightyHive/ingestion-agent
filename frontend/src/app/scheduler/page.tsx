"use client"

import { useRouter } from "next/navigation"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import ScheduleFrequencyCard from "@/components/scheduler/ScheduleFrequencyCard"

export default function SchedulerPage() {
  const router = useRouter()
  const { schemaProposal, isProposing, proposalError } = useConnectorStore()

  if (schemaProposal) {
    return (
      <div className="space-y-6 max-w-[1200px]">
        <div>
          <h1 className="text-2xl font-semibold text-on-surface">Scheduler</h1>
          <p className="text-sm text-on-surface-variant mt-0.5">
            Configure how often data syncs for <span className="font-medium text-on-surface">{schemaProposal.tableName}</span>.
          </p>
        </div>
        <div className="flex justify-center min-h-[40vh] items-start">
          <ScheduleFrequencyCard />
        </div>
      </div>
    )
  }

  if (isProposing) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <span className="material-symbols-outlined text-4xl text-on-surface-variant animate-pulse">
          calendar_today
        </span>
        <p className="text-sm text-on-surface-variant text-center max-w-sm">
          The schema is still being generated. Open the Schema step to follow progress, then return here to schedule.
        </p>
        <button
          type="button"
          onClick={() => router.push("/schema")}
          className="text-sm font-semibold text-primary hover:underline"
        >
          Go to Schema
        </button>
      </div>
    )
  }

  if (proposalError) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <span className="material-symbols-outlined text-4xl text-on-surface-variant">error</span>
        <p className="text-sm text-on-surface-variant text-center max-w-sm">
          Schema generation failed. Fix the issue on the Schema or Selectors step before configuring a schedule.
        </p>
        <p className="text-xs text-red-600 max-w-md text-center">{proposalError}</p>
        <div className="flex flex-wrap items-center justify-center gap-4">
          <button
            type="button"
            onClick={() => router.push("/schema")}
            className="text-sm font-semibold text-primary hover:underline"
          >
            Go to Schema
          </button>
          <button
            type="button"
            onClick={() => router.push("/selectors")}
            className="text-sm font-semibold text-primary hover:underline"
          >
            Go to Selectors
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center justify-center gap-4 py-20">
      <span className="material-symbols-outlined text-4xl text-on-surface-variant">calendar_today</span>
      <p className="text-sm text-on-surface-variant text-center max-w-sm">
        There is no schema to schedule yet. Complete the Schema step first.
      </p>
      <button
        type="button"
        onClick={() => router.push("/schema")}
        className="text-sm font-semibold text-primary hover:underline"
      >
        Go to Schema
      </button>
    </div>
  )
}
