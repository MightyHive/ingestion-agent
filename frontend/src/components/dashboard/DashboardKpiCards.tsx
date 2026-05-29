"use client"

import Link from "next/link"
import PlatformLogo from "@/components/platforms/PlatformLogo"
import { getCredentialPlatformLabel } from "@/lib/platforms/credential-platforms"
import {
  daysUntil,
  fmtRelative,
  getFailedPipelinesFromJobs,
  isExpiringSoon,
  isHealthyConnectionStatus,
} from "@/lib/dashboard-utils"
import { demoFailedPipelines } from "@/lib/mock-data"
import { useCredentialStore } from "@/lib/stores/credentialStore"
import { useExportJobStore } from "@/lib/stores/exportJobStore"
import { useTemplateStore } from "@/lib/stores/templateStore"

function KpiShell({
  title,
  icon,
  iconColor,
  count,
  status,
  children,
  footer,
}: {
  title: string
  icon: string
  iconColor: string
  count: number | string
  status?: "ok" | "warn" | "error"
  children?: React.ReactNode
  footer?: React.ReactNode
}) {
  const dot =
    status === "error"
      ? "bg-red-500"
      : status === "warn"
        ? "bg-amber-400"
        : "bg-emerald-500"

  return (
    <div className="bg-card rounded-2xl border border-border p-5 flex flex-col gap-4 min-h-[220px]">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className={`material-symbols-outlined text-lg ${iconColor}`}>{icon}</span>
          <h3 className="text-sm font-semibold text-on-surface">{title}</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-3xl font-bold text-on-surface leading-none">{count}</span>
          {status && <span className={`w-2 h-2 rounded-full ${dot}`} />}
        </div>
      </div>
      {children}
      {footer}
    </div>
  )
}

export default function DashboardKpiCards() {
  const credentials = useCredentialStore((s) => s.credentials)
  const jobs = useExportJobStore((s) => s.jobs)
  const templates = useTemplateStore((s) => s.templates)

  const templateNameById = Object.fromEntries(
    templates.map((t) => [t.id, t.tableName || t.platform])
  )

  const expiringCredentials = credentials.filter((c) => isExpiringSoon(c.tokenExpiresAt))
  const healthyCount = credentials.filter((c) => isHealthyConnectionStatus(c.status)).length
  const brokenCount = credentials.length - healthyCount

  const failedFromJobs = getFailedPipelinesFromJobs(jobs, templateNameById)
  const failedPipelines =
    jobs.length > 0
      ? failedFromJobs
      : demoFailedPipelines.map((p) => ({
          id: p.id,
          name: p.name,
          platform: p.platform,
          lastFailedAt: p.lastSync,
        }))

  const connectionRatio = credentials.length === 0 ? "—" : `${healthyCount}/${credentials.length}`

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <KpiShell
        title="Credentials expiring soon"
        icon="key"
        iconColor="text-amber-500"
        count={expiringCredentials.length}
        status={expiringCredentials.length > 0 ? "warn" : "ok"}
        footer={
          expiringCredentials.length > 0 ? (
            <Link href="/credentials-library" className="text-xs font-semibold text-primary hover:underline">
              Manage credentials →
            </Link>
          ) : undefined
        }
      >
        {expiringCredentials.length === 0 ? (
          <p className="text-sm text-on-surface-variant">No tokens expiring within 7 days.</p>
        ) : (
          <ul className="space-y-2">
            {expiringCredentials.slice(0, 4).map((cred) => {
              const days = cred.tokenExpiresAt ? daysUntil(cred.tokenExpiresAt) : null
              return (
                <li
                  key={cred.id}
                  className="flex items-center justify-between gap-2 text-sm py-1.5 px-2 rounded-lg bg-amber-50/80"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <PlatformLogo platform={cred.platform} size="sm" />
                    <span className="truncate text-on-surface">{cred.name}</span>
                  </div>
                  <span className="text-xs font-semibold text-amber-700 whitespace-nowrap">
                    {days !== null && days <= 0 ? "Expired" : `${days}d left`}
                  </span>
                </li>
              )
            })}
          </ul>
        )}
      </KpiShell>

      <KpiShell
        title="Pipelines that failed"
        icon="sync_problem"
        iconColor="text-red-500"
        count={failedPipelines.length}
        status={failedPipelines.length > 0 ? "error" : "ok"}
        footer={
          failedPipelines.length > 0 ? (
            <Link href="/export-planner" className="text-xs font-semibold text-primary hover:underline">
              View in Export Scheduler →
            </Link>
          ) : undefined
        }
      >
        {failedPipelines.length === 0 ? (
          <p className="text-sm text-on-surface-variant">All recent pipeline runs succeeded.</p>
        ) : (
          <ul className="space-y-2">
            {failedPipelines.slice(0, 4).map((pipeline) => (
              <li
                key={pipeline.id}
                className="flex items-center justify-between gap-2 text-sm py-1.5 px-2 rounded-lg bg-red-50/80"
              >
                <div className="min-w-0">
                  <p className="truncate font-medium text-on-surface">{pipeline.name}</p>
                  <p className="text-xs text-on-surface-variant">{pipeline.platform}</p>
                </div>
                <span className="text-xs text-red-600 whitespace-nowrap">
                  {fmtRelative(pipeline.lastFailedAt)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </KpiShell>

      <KpiShell
        title="Connection health"
        icon="link"
        iconColor="text-emerald-500"
        count={connectionRatio}
        status={brokenCount > 0 ? "warn" : "ok"}
        footer={
          <Link href="/credentials-library" className="text-xs font-semibold text-primary hover:underline">
            View all connections →
          </Link>
        }
      >
        <div className="space-y-3">
          <div className="flex h-2 rounded-full overflow-hidden bg-border">
            {credentials.length > 0 && (
              <>
                <div
                  className="bg-emerald-500 transition-all"
                  style={{ width: `${(healthyCount / credentials.length) * 100}%` }}
                />
                <div
                  className="bg-red-400 transition-all"
                  style={{ width: `${(brokenCount / credentials.length) * 100}%` }}
                />
              </>
            )}
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-emerald-700 font-medium">{healthyCount} healthy</span>
            <span className="text-red-600 font-medium">{brokenCount} broken</span>
          </div>
          {brokenCount > 0 && (
            <ul className="space-y-1">
              {credentials
                .filter((c) => !isHealthyConnectionStatus(c.status))
                .slice(0, 3)
                .map((cred) => (
                  <li key={cred.id} className="text-xs text-on-surface-variant flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-400 flex-shrink-0" />
                    <span className="truncate">
                      {cred.name} · {getCredentialPlatformLabel(cred.platform)}
                    </span>
                  </li>
                ))}
            </ul>
          )}
        </div>
      </KpiShell>
    </div>
  )
}
