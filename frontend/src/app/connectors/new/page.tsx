"use client"

import { useSearchParams, useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import { useAgentStream } from "@/lib/hooks/useAgentStream"
import { getConnectorSessionId } from "@/lib/sessions"
import ColumnSelector, { type Column } from "@/components/connectors/ColumnSelector"
import { columnsFromUiTriggerData } from "@/lib/ui-trigger-fields"
import { cn } from "@/lib/utils"

// ── Static connector metadata ─────────────────────────────────────────────────

const CONNECTOR_META: Record<
  string,
  { name: string; color: string; initial: string; authMethod: string }
> = {
  meta: {
    name: "Meta Ads",
    color: "#1877F2",
    initial: "M",
    authMethod: "OAuth 2.0",
  },
  tiktok: {
    name: "TikTok Ads",
    color: "#010101",
    initial: "T",
    authMethod: "OAuth 2.0",
  },
  youtube: {
    name: "YouTube Analytics",
    color: "#FF0000",
    initial: "Y",
    authMethod: "OAuth 2.0",
  },
}

// ── Agent node display names ───────────────────────────────────────────────────

const NODE_LABELS: Record<string, string> = {
  coordinator: "Coordinating Agent",
  api_researcher: "API Researcher",
  data_architect: "Data Architect",
  software_engineer: "Software Engineer",
  qa_security: "QA & Security",
  devops: "DevOps Agent",
}

// ── Wizard steps ──────────────────────────────────────────────────────────────

type WizardStep = "select" | "auth" | "agent" | "done"

const STEP_LABELS = ["Configuration", "Authentication", "Agent Setup", "Complete"]

function StepIndicator({
  current,
}: {
  current: WizardStep
}) {
  const steps: WizardStep[] = ["select", "auth", "agent", "done"]
  const idx = steps.indexOf(current)
  return (
    <div className="flex items-center gap-2">
      {STEP_LABELS.map((label, i) => (
        <div key={label} className="flex items-center gap-2">
          <div
            className={cn(
              "h-1.5 rounded-full transition-all",
              i < idx
                ? "w-8 bg-primary"
                : i === idx
                ? "w-8 bg-primary"
                : "w-8 bg-border"
            )}
          />
        </div>
      ))}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function NewConnectorPage() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const preselected = searchParams.get("connector") ?? ""

  const [step, setStep] = useState<WizardStep>(preselected ? "auth" : "select")
  const [connectorId, setConnectorId] = useState(preselected)
  const [sessionId] = useState(() =>
    getConnectorSessionId(preselected || "new")
  )

  const { isLoading, completedNodes, finalResponse, error, startChat, submitInput, reset } =
    useAgentStream()

  const meta = CONNECTOR_META[connectorId]

  // When the agent returns a final response, move to agent step to show result
  useEffect(() => {
    if (finalResponse) setStep("agent")
  }, [finalResponse])

  // ── Step: Choose connector ─────────────────────────────────────────────────

  function handleSelectConnector(id: string) {
    setConnectorId(id)
    setStep("auth")
  }

  // ── Step: Auth → trigger agent ────────────────────────────────────────────

  function handleConnect() {
    if (!connectorId) return
    setStep("agent")
    reset()
    startChat(sessionId, `Quiero conectar ${meta.name}`)
  }

  // ── Step: ColumnSelector submit ───────────────────────────────────────────

  function handleColumnsConfirm(columns: string[]) {
    reset()
    submitInput(sessionId, { columns })
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="max-w-[1100px] space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-semibold text-primary uppercase tracking-wider">
            Step{" "}
            {{ select: 1, auth: 2, agent: 3, done: 4 }[step]} of 4 ·{" "}
            {
              {
                select: "Select connector",
                auth: "Authentication",
                agent: "Agent setup",
                done: "Complete",
              }[step]
            }
          </p>
          <h1 className="text-2xl font-semibold text-on-surface mt-1">
            {step === "select" && "Choose your data source"}
            {step === "auth" && "Configure authentication"}
            {step === "agent" && "Setting up your connector"}
            {step === "done" && "Connector ready"}
          </h1>
        </div>
        <StepIndicator current={step} />
      </div>

      {/* Layout: main + sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-6">
        {/* ── MAIN PANEL ── */}
        <div className="bg-card rounded-2xl border border-border p-6 flex flex-col gap-6">

          {/* Step: Select connector */}
          {step === "select" && (
            <ConnectorGrid onSelect={handleSelectConnector} selected={connectorId} />
          )}

          {/* Step: Auth */}
          {step === "auth" && meta && (
            <div className="flex flex-col gap-6">
              <div className="p-4 rounded-xl bg-muted/50 border border-border text-sm text-on-surface-variant">
                You need to authorize{" "}
                <span className="font-semibold text-on-surface">
                  Media Data Studio
                </span>{" "}
                to access your {meta.name} assets. This uses{" "}
                <span className="font-semibold text-on-surface">{meta.authMethod}</span>{" "}
                and is fully revocable at any time.
              </div>
              <ul className="space-y-2">
                {getPrerequisites(connectorId).map((req) => (
                  <li key={req} className="flex items-center gap-2 text-sm text-on-surface">
                    <span className="material-symbols-outlined text-primary text-base">
                      check_circle
                    </span>
                    {req}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Step: Agent in progress */}
          {step === "agent" && (
            <div className="flex flex-col gap-4">
              {/* Progress nodes */}
              {(isLoading || completedNodes.length > 0) && (
                <div className="space-y-2">
                  <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
                    Agent progress
                  </p>
                  {completedNodes.map((node) => (
                    <div
                      key={node}
                      className="flex items-center gap-3 px-3 py-2 rounded-lg bg-emerald-50 border border-emerald-200"
                    >
                      <span className="material-symbols-outlined text-emerald-600 text-base">
                        check_circle
                      </span>
                      <span className="text-sm font-medium text-emerald-800">
                        {NODE_LABELS[node] ?? node}
                      </span>
                    </div>
                  ))}
                  {isLoading && (
                    <div className="flex items-center gap-3 px-3 py-2 rounded-lg bg-blue-50 border border-blue-200">
                      <span className="material-symbols-outlined text-blue-600 text-base animate-spin">
                        sync
                      </span>
                      <span className="text-sm font-medium text-blue-800">
                        Thinking...
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Final response text */}
              {finalResponse?.response_text && (
                <div className="flex items-start gap-3 p-3 rounded-xl bg-accent/40 border border-accent">
                  <span className="material-symbols-outlined text-primary text-base mt-0.5 flex-shrink-0">
                    smart_toy
                  </span>
                  <p className="text-sm text-on-surface">
                    {finalResponse.response_text}
                  </p>
                </div>
              )}

              {/* Dynamic UI trigger */}
              {finalResponse?.requires_human_input &&
                finalResponse.ui_trigger && (
                  <DynamicComponent
                    trigger={finalResponse.ui_trigger}
                    onConfirm={handleColumnsConfirm}
                    isLoading={isLoading}
                  />
                )}

              {/* Error */}
              {error && (
                <div className="flex items-center gap-2 p-3 rounded-xl bg-red-50 border border-red-200 text-sm text-red-700">
                  <span className="material-symbols-outlined text-base">error</span>
                  {error}
                </div>
              )}
            </div>
          )}

          {/* Back / Continue buttons */}
          <div className="flex items-center justify-between mt-auto pt-4 border-t border-border">
            <button
              onClick={() => {
                if (step === "auth") setStep("select")
                else if (step === "select") router.push("/connectors")
                else router.push("/connectors")
              }}
              className="flex items-center gap-1 text-sm text-on-surface-variant hover:text-on-surface transition-colors"
            >
              <span className="material-symbols-outlined text-base">arrow_back</span>
              Back
            </button>

            {step === "auth" && (
              <button
                onClick={handleConnect}
                className="flex items-center gap-2 px-5 py-2 bg-primary text-white text-sm font-semibold rounded-xl hover:bg-primary/90 transition-colors"
              >
                <span className="material-symbols-outlined text-base">link</span>
                Connect Account
              </button>
            )}
          </div>
        </div>

        {/* ── SIDEBAR ── */}
        <div className="flex flex-col gap-4">
          {/* Connector info card */}
          {meta && (
            <div className="bg-card rounded-2xl border border-border p-5 flex flex-col gap-4">
              <div className="flex items-center gap-3">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center text-white font-bold text-base flex-shrink-0"
                  style={{ backgroundColor: meta.color }}
                >
                  {meta.initial}
                </div>
                <div>
                  <p className="text-sm font-semibold text-on-surface">{meta.name}</p>
                  <p className="text-xs text-on-surface-variant">
                    Configure Authentication
                  </p>
                </div>
              </div>
              <div>
                <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-1">
                  Auth method
                </p>
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-on-surface">{meta.authMethod}</p>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                    Secure
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Session info */}
          <div className="bg-card rounded-2xl border border-border p-5">
            <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-2">
              Session
            </p>
            <p className="text-xs font-mono text-on-surface-variant break-all">
              {sessionId}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Subcomponents ─────────────────────────────────────────────────────────────

function ConnectorGrid({
  onSelect,
  selected,
}: {
  onSelect: (id: string) => void
  selected: string
}) {
  const connectors = Object.entries(CONNECTOR_META)
  return (
    <div>
      <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-3">
        Available connectors
      </p>
      <div className="grid grid-cols-2 gap-3">
        {connectors.map(([id, m]) => (
          <button
            key={id}
            onClick={() => onSelect(id)}
            className={cn(
              "flex items-center gap-3 p-3 rounded-xl border text-left transition-all",
              selected === id
                ? "border-primary/50 bg-primary/5"
                : "border-border hover:bg-muted/50"
            )}
          >
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center text-white font-bold text-sm flex-shrink-0"
              style={{ backgroundColor: m.color }}
            >
              {m.initial}
            </div>
            <span className="text-sm font-medium text-on-surface">{m.name}</span>
            {selected === id && (
              <span className="material-symbols-outlined text-primary text-base ml-auto">
                check_circle
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}

function DynamicComponent({
  trigger,
  onConfirm,
  isLoading,
}: {
  trigger: { component: string; message?: string; data?: Record<string, unknown> }
  onConfirm: (columns: string[]) => void
  isLoading: boolean
}) {
  switch (trigger.component) {
    case "ColumnSelector": {
      const fromApi = columnsFromUiTriggerData(trigger.data)
      const columns: Column[] = fromApi.length ? fromApi : PLACEHOLDER_COLUMNS
      return (
        <ColumnSelector
          message={trigger.message ?? "Select columns for ingestion"}
          columns={columns}
          onConfirm={onConfirm}
          isLoading={isLoading}
        />
      )
    }

    case "SchemaApproval": {
      const ddl = typeof trigger.data?.ddl === "string" ? trigger.data.ddl : ""
      return (
        <div className="p-4 rounded-xl border border-border bg-card text-sm space-y-2">
          <p className="font-semibold text-on-surface">{trigger.message ?? "Schema approval"}</p>
          {ddl ? (
            <pre className="text-xs font-mono whitespace-pre-wrap break-words max-h-64 overflow-auto bg-muted p-3 rounded-lg">
              {ddl}
            </pre>
          ) : (
            <p className="text-on-surface-variant">No DDL in trigger payload.</p>
          )}
        </div>
      )
    }

    case "AuthForm":
      return (
        <div className="p-4 rounded-xl border border-amber-200 bg-amber-50 text-sm text-amber-800">
          <p className="font-semibold mb-1">Authentication required</p>
          <p>{trigger.message ?? ""}</p>
        </div>
      )

    default:
      return (
        <div className="p-3 rounded-xl border border-border bg-muted text-sm text-on-surface-variant">
          <span className="font-mono">{trigger.component}</span>: {trigger.message ?? ""}
        </div>
      )
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function getPrerequisites(connectorId: string): string[] {
  const map: Record<string, string[]> = {
    meta: [
      "Business Manager Admin access required",
      "Active pixel for conversion data",
    ],
    tiktok: [
      "TikTok For Business account required",
      "Advertiser-level permissions",
    ],
    youtube: [
      "Google account with channel ownership",
      "YouTube Analytics API enabled in GCP",
    ],
  }
  return map[connectorId] ?? []
}

// Placeholder columns shown when the backend hasn't provided the list yet
// (in production these come from trigger.data.columns)
const PLACEHOLDER_COLUMNS: Column[] = [
  { id: "campaign_name", name: "Campaign Name", type: "STRING", description: "Descriptive name of the campaign" },
  { id: "campaign_id", name: "Campaign ID", type: "INTEGER", description: "Unique campaign identifier" },
  { id: "ad_set_name", name: "Ad Set Name", type: "STRING" },
  { id: "impressions", name: "Impressions", type: "INTEGER", description: "Times the ad was shown" },
  { id: "spend", name: "Spend", type: "FLOAT", description: "Total amount spent" },
  { id: "clicks", name: "Clicks", type: "INTEGER" },
  { id: "ctr", name: "CTR", type: "FLOAT", description: "Click-through rate" },
  { id: "conversions", name: "Conversions", type: "INTEGER" },
  { id: "reach", name: "Reach", type: "INTEGER" },
  { id: "frequency", name: "Frequency", type: "FLOAT" },
  { id: "event_date", name: "Event Date", type: "DATE" },
  { id: "account_id", name: "Account ID", type: "STRING" },
]