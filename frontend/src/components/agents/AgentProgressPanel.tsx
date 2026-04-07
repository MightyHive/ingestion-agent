"use client"

import { cn } from "@/lib/utils"

/** LangGraph node id → human-readable label for progress UI. */
export const DEFAULT_AGENT_NODE_LABELS: Record<string, string> = {
  coordinator: "Coordinating Agent",
  api_researcher: "API Researcher",
  data_architect: "Data Architect",
  software_engineer: "Software Engineer",
  synthesizer: "Synthesizer",
  prepare_new_turn: "Preparing turn",
  sync_barrier: "Sync",
}

type AgentProgressPanelProps = {
  /** Node ids completed in order (from SSE `progress` events). */
  completedNodes: readonly string[]
  /** True while the stream is still running (show in-flight row). */
  active: boolean
  /** Optional override or extension of default labels. */
  nodeLabels?: Record<string, string>
  /** Accessible label for the progress region. */
  ariaLabel?: string
  className?: string
}

/**
 * Shows completed agent steps and a working indicator while the pipeline runs.
 */
export function AgentProgressPanel({
  completedNodes,
  active,
  nodeLabels,
  ariaLabel = "Agent progress",
  className,
}: AgentProgressPanelProps) {
  const labels = { ...DEFAULT_AGENT_NODE_LABELS, ...nodeLabels }

  if (!active && completedNodes.length === 0) {
    return null
  }

  return (
    <div
      className={cn("flex flex-col gap-3", className)}
      role="status"
      aria-live="polite"
      aria-label={ariaLabel}
    >
      <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
        Agent progress
      </p>
      <div className="flex flex-col gap-2">
        {completedNodes.map((node) => (
          <div
            key={node}
            className="flex items-center gap-3 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-200"
          >
            <span className="material-symbols-outlined text-emerald-600 text-base shrink-0">
              check_circle
            </span>
            <span className="text-sm font-medium text-emerald-800">
              {labels[node] ?? node}
            </span>
          </div>
        ))}
        {active && (
          <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-blue-50 border border-blue-200">
            <span className="material-symbols-outlined text-blue-600 text-base animate-spin shrink-0">
              sync
            </span>
            <span className="text-sm font-medium text-blue-800">Working…</span>
          </div>
        )}
      </div>
    </div>
  )
}
