"use client"

import { useCallback, useMemo } from "react"
import PlatformLogo from "@/components/platforms/PlatformLogo"
import { cn } from "@/lib/utils"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import { useCredentialStore } from "@/lib/stores/credentialStore"
import { getReportEndpoints } from "@/lib/platforms/registry"
import {
  connectorIdToCredentialPlatform,
  platformsMatch,
} from "@/lib/platforms/platform-map"
import { getCredentialPlatformLabel } from "@/lib/platforms/credential-platforms"

export type CredentialScopeData = {
  credentialIds: string[]
  reportingLevel: string | null
}

function resolveScopeLabel(
  endpoints: readonly { id: string; label: string }[],
  id: string | null
): string {
  if (!id) return "—"
  return endpoints.find((e) => e.id === id)?.label ?? id
}

interface Props {
  data: CredentialScopeData
  onUpdate: (d: Partial<CredentialScopeData>) => void
  fieldCount?: number
}

export default function CredentialScopeStep({ data, onUpdate, fieldCount = 0 }: Props) {
  const { connectorId, connectorName } = useConnectorStore()
  const { credentials } = useCredentialStore()

  const credentialPlatform = connectorIdToCredentialPlatform(connectorId)
  const endpoints = useMemo(() => getReportEndpoints(connectorId ?? "meta"), [connectorId])

  const compatibleCredentials = useMemo(() => {
    if (!credentialPlatform) return []
    return credentials.filter((c) => platformsMatch(c.platform, credentialPlatform))
  }, [credentials, credentialPlatform])

  const selectedCredentials = data.credentialIds
    .map((id) => credentials.find((c) => c.id === id))
    .filter(Boolean)

  const scopeLabel = resolveScopeLabel(endpoints, data.reportingLevel)

  const toggleCredential = useCallback(
    (id: string) => {
      const exists = data.credentialIds.includes(id)
      onUpdate({
        credentialIds: exists
          ? data.credentialIds.filter((c) => c !== id)
          : [...data.credentialIds, id],
      })
    },
    [data.credentialIds, onUpdate]
  )

  const handleSetReportingLevel = (id: string) => {
    onUpdate({ reportingLevel: id })
  }

  if (!connectorId) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20">
        <span className="material-symbols-outlined text-4xl text-on-surface-variant">hub</span>
        <p className="text-sm text-on-surface-variant">Select a connector first.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div>
        <h2 className="text-2xl font-semibold text-on-surface">Credentials &amp; reporting scope</h2>
        <p className="text-sm text-on-surface-variant mt-0.5">
          Choose which credentials to use and the reporting level for {connectorName ?? "your connector"}.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-6">
        <div className="space-y-6">
          <section className="bg-card rounded-2xl border border-border p-6 space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-on-surface">1. Select credentials</h3>
              <p className="text-sm text-on-surface-variant mt-1">
                {credentialPlatform
                  ? `Showing ${getCredentialPlatformLabel(credentialPlatform)} credentials.`
                  : "No credential platform mapping for this connector."}
              </p>
            </div>

            {compatibleCredentials.length === 0 ? (
              <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                No credentials found for this platform. Add one in Platform Credentials first.
              </p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {compatibleCredentials.map((cred) => {
                  const isSelected = data.credentialIds.includes(cred.id)
                  return (
                    <button
                      key={cred.id}
                      type="button"
                      onClick={() => toggleCredential(cred.id)}
                      className={cn(
                        "flex items-start gap-3 rounded-xl border p-4 text-left transition-all",
                        isSelected
                          ? "border-primary bg-primary/5 ring-2 ring-primary/20"
                          : "border-border hover:border-primary/30"
                      )}
                    >
                      <PlatformLogo platform={cred.platform} size="sm" />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-on-surface">{cred.name}</p>
                        <p className="text-xs text-on-surface-variant">
                          {cred.market} · {cred.brand}
                        </p>
                        {cred.status && (
                          <p
                            className={cn(
                              "text-xs mt-1 font-medium",
                              cred.status === "Healthy" ? "text-emerald-600" : "text-amber-600"
                            )}
                          >
                            {cred.status}
                          </p>
                        )}
                      </div>
                      {isSelected && (
                        <span className="material-symbols-outlined text-primary text-base shrink-0">
                          check_circle
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
            )}
          </section>

          <section className="bg-card rounded-2xl border border-border p-6 space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-on-surface">2. Reporting scope</h3>
              <p className="text-sm text-on-surface-variant mt-1">
                Sets the grain of each row in your extract.
              </p>
            </div>

            <div
              className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2"
              role="listbox"
              aria-label="Reporting level"
            >
              {endpoints.map((ep) => {
                const active = data.reportingLevel === ep.id
                return (
                  <button
                    key={ep.id}
                    type="button"
                    role="option"
                    aria-selected={active}
                    onClick={() => handleSetReportingLevel(ep.id)}
                    className={cn(
                      "text-left rounded-xl border px-4 py-3 transition-colors",
                      active
                        ? "border-primary bg-primary/5 ring-1 ring-primary/20"
                        : "border-border hover:bg-muted/50"
                    )}
                  >
                    <p className="text-sm font-semibold text-on-surface">{ep.label}</p>
                    <p className="text-xs text-on-surface-variant mt-0.5">
                      One row per {ep.label.toLowerCase()}
                    </p>
                  </button>
                )
              })}
            </div>

            {!data.reportingLevel && (
              <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                Select a reporting level to continue.
              </p>
            )}
          </section>
        </div>

        <aside className="bg-card rounded-2xl border border-border p-5 h-fit sticky top-24 space-y-4">
          <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider">
            Live preview
          </p>

          <PreviewRow label="Connector" value={connectorName ?? "—"} />
          <PreviewRow
            label="Credentials"
            value={
              selectedCredentials.length > 0
                ? selectedCredentials.map((c) => c!.name).join(", ")
                : "None selected"
            }
          />
          <PreviewRow label="Reporting scope" value={scopeLabel} />
          <PreviewRow
            label="Fields selected"
            value={fieldCount > 0 ? `${fieldCount} fields` : "— (next step)"}
          />

          {data.credentialIds.length > 0 && data.reportingLevel && (
            <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-3 py-2 text-xs text-emerald-800">
              Ready to select fields in the next step.
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}

function PreviewRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">{label}</p>
      <p className="text-sm font-medium text-on-surface mt-0.5 break-words">{value}</p>
    </div>
  )
}
