import Link from "next/link"
import {
  kpiMetrics, alerts, recentActivity, pipelines,
  connectorHealth, onboardingSteps, quickActions,
  type KpiStatus, type AlertSeverity, type AlertType,
  type ActivityStatus, type ActivityType,
  type PipelineStatus, type TokenHealth,
} from "@/lib/mock-data"
import {
  Table, TableBody, TableCell, TableHead,
  TableHeader, TableRow,
} from "@/components/ui/table"

// ── Helpers ───────────────────────────────────────────────────────────────────

function kpiStatusDot(status: KpiStatus) {
  return { ok: "bg-emerald-500", warn: "bg-amber-400", error: "bg-red-500" }[status]
}

function alertBadge(severity: AlertSeverity) {
  return {
    critical: "bg-red-100 text-red-700 border border-red-200",
    warning:  "bg-amber-100 text-amber-700 border border-amber-200",
    info:     "bg-blue-100 text-blue-700 border border-blue-200",
  }[severity]
}

function alertIcon(type: AlertType) {
  return {
    token_expiry: "key",
    sync_failure: "sync_problem",
    schema_drift: "schema",
    rate_limit:   "speed",
    info:         "info",
  }[type]
}

function activityIcon(type: ActivityType): { icon: string; bg: string; color: string } {
  return {
    sync:   { icon: "sync_alt",      bg: "bg-blue-50",   color: "text-blue-600" },
    agent:  { icon: "smart_toy",     bg: "bg-purple-50", color: "text-purple-600" },
    schema: { icon: "schema",        bg: "bg-slate-100", color: "text-slate-600" },
    deploy: { icon: "rocket_launch", bg: "bg-emerald-50",color: "text-emerald-600" },
    token:  { icon: "key",           bg: "bg-amber-50",  color: "text-amber-600" },
  }[type]
}

function activityStatusIcon(status: ActivityStatus) {
  return {
    success: { icon: "check_circle", cls: "text-emerald-500" },
    failed:  { icon: "cancel",       cls: "text-red-500" },
    running: { icon: "sync",         cls: "text-blue-500 animate-spin" },
    pending: { icon: "schedule",     cls: "text-amber-500" },
  }[status]
}

function pipelineStatusBadge(status: PipelineStatus) {
  return {
    active:  "bg-emerald-100 text-emerald-700",
    syncing: "bg-blue-100 text-blue-700",
    paused:  "bg-slate-100 text-slate-600",
    error:   "bg-red-100 text-red-700",
  }[status]
}

function tokenBadge(health: TokenHealth, days?: number) {
  if (health === "ok") return null
  if (health === "expired") return { label: "Expirado", cls: "bg-red-100 text-red-700" }
  return { label: `${days}d`, cls: "bg-amber-100 text-amber-700" }
}

function connectorStatusDot(status: string) {
  return { healthy: "bg-emerald-500", degraded: "bg-amber-400", down: "bg-red-500" }[status] ?? "bg-slate-300"
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })
}

function fmtRelative(iso: string) {
  const diff = Date.now() - new Date(iso).getTime()
  const h = Math.floor(diff / 3600000)
  const m = Math.floor(diff / 60000)
  if (h > 0) return `${h}h ago`
  return `${m}m ago`
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function Home() {
  // Derived from data: if no pipelines exist, treat user as new client.
  // Mock: empty the pipelines array in mock-data.ts to simulate onboarding.
  // Real backend: pipelines will come from a fetch() — this works automatically.
  const IS_NEW_CLIENT = pipelines.length === 0 
  
  const criticalAlerts = alerts.filter(a => a.severity === "critical")

  return (
    <div className="space-y-6 max-w-[1400px]">

      {/* Título */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-on-surface">Dashboard</h1>
          <p className="text-sm text-on-surface-variant mt-0.5">
            Overview of your ingestion infrastructure
          </p>
        </div>
        {criticalAlerts.length > 0 && !IS_NEW_CLIENT &&(
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-red-50 border border-red-200">
            <span className="material-symbols-outlined text-red-600 text-base">warning</span>
            <span className="text-sm font-semibold text-red-700">
              {criticalAlerts.length} critical alert{criticalAlerts.length > 1 ? "s" : ""}
            </span>
          </div>
        )}
      </div>

      {/* ── ONBOARDING (cliente sin pipelines) ── */}
      {IS_NEW_CLIENT && (
        <div className="bg-card rounded-2xl border border-border p-6 flex flex-col gap-4">
          <div className="flex items-center gap-3">
            <span className="material-symbols-outlined text-primary text-2xl">rocket_launch</span>
            <div>
              <h2 className="font-semibold text-on-surface">Start connecting your data</h2>
              <p className="text-sm text-on-surface-variant">Follow these steps to create your first pipeline</p>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {onboardingSteps.map((step, i) => (
              <Link
                key={step.id}
                href={step.href}
                className="flex flex-col gap-2 p-4 rounded-xl border border-border hover:border-primary/40 hover:bg-primary/5 transition-all"
              >
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${step.done ? "bg-emerald-500 text-white" : "bg-muted text-on-surface-variant"}`}>
                  {step.done ? "✓" : i + 1}
                </div>
                <span className="text-sm font-medium text-on-surface">{step.label}</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* ── KPIs ── */}
      {!IS_NEW_CLIENT && (
        <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-4">
          {kpiMetrics.map((kpi) => (
            <div key={kpi.id} className="bg-card rounded-2xl p-4 shadow-sm border border-border flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-on-surface-variant truncate">{kpi.label}</span>
                <span className={`w-2 h-2 rounded-full flex-shrink-0 ${kpiStatusDot(kpi.status)}`} />
              </div>
              <div className="flex items-end gap-1">
                <span className="text-2xl font-bold text-on-surface leading-none">{kpi.value}</span>
                {kpi.unit && <span className="text-sm text-on-surface-variant mb-0.5">{kpi.unit}</span>}
              </div>
              {kpi.sub && (
                <span className="text-xs text-on-surface-variant">{kpi.sub}</span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ── Row 2: Needs Attention + Quick Actions ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* Needs Attention — existing clients only */}
        {!IS_NEW_CLIENT && (
        <div className="lg:col-span-2 bg-card rounded-2xl shadow-sm border border-border p-5 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-on-surface flex items-center gap-2">
              <span className="material-symbols-outlined text-amber-500 text-lg">warning</span>
              Needs Attention
            </h2>
            <span className="text-xs text-on-surface-variant">{alerts.length} items</span>
          </div>
          <div className="space-y-2">
            {alerts.map((alert) => (
              <div key={alert.id} className="flex items-start gap-3 p-3 rounded-xl bg-surface-container-low">
                <div className={`flex items-center gap-1.5 text-xs font-semibold px-2 py-0.5 rounded-full flex-shrink-0 mt-0.5 ${alertBadge(alert.severity)}`}>
                  <span className="material-symbols-outlined text-xs">{alertIcon(alert.type)}</span>
                  {alert.severity}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-on-surface-variant">{alert.source}</p>
                  <p className="text-sm text-on-surface mt-0.5">{alert.description}</p>
                </div>
                {alert.cta && (
                  <button className="flex-shrink-0 text-xs font-semibold text-primary hover:underline whitespace-nowrap">
                    {alert.cta}
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
        )}

        {/* Quick Actions */}
        <div className="bg-card rounded-2xl shadow-sm border border-border p-5 flex flex-col gap-4">
          <h2 className="font-semibold text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-lg">bolt</span>
            Quick Actions
          </h2>
          <div className="grid grid-cols-2 gap-2">
            {quickActions.map((qa) => (
              <Link
                key={qa.id}
                href={qa.href}
                className="flex flex-col items-center gap-2 p-3 rounded-xl bg-muted/50 hover:bg-muted transition-colors"
              >
                <span className="material-symbols-outlined text-primary text-xl">{qa.icon}</span>
                <span className="text-xs font-medium text-on-surface text-center">{qa.label}</span>
              </Link>
            ))}
          </div>

          {/* Connector health mini */}
          <div className="pt-2 border-t border-border">
            <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-2">
              Connector Health
            </p>
            {connectorHealth.map((ch) => {
              const tb = tokenBadge(ch.tokenHealth, ch.tokenDaysLeft)
              return (
                <div key={ch.id} className="flex items-center justify-between py-1.5">
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${connectorStatusDot(ch.status)}`} />
                    <span className="text-xs text-on-surface">{ch.name}</span>
                  </div>
                  {tb && (
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full ${tb.cls}`}>
                      {tb.label}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* ── Row 3: Recent Activity + Pipelines — existing clients only ── */}
      {!IS_NEW_CLIENT && <>
      <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-4">

        {/* Recent Activity */}
        <div className="bg-card rounded-2xl shadow-sm border border-border p-5 flex flex-col gap-3">
          <h2 className="font-semibold text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-lg">history</span>
            Recent Activity
          </h2>
          <div className="space-y-1">
            {recentActivity.map((event) => {
              const typeInfo  = activityIcon(event.type)
              const statusInfo = activityStatusIcon(event.status)
              return (
                <div key={event.id} className="flex items-start gap-3 px-2 py-2 rounded-lg hover:bg-surface-container-low transition-colors">
                  {/* Tipo icon */}
                  <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5 ${typeInfo.bg}`}>
                    <span className={`material-symbols-outlined text-sm ${typeInfo.color}`}>
                      {typeInfo.icon}
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-on-surface leading-snug">{event.title}</p>
                    {event.meta && (
                      <p className="text-xs text-on-surface-variant mt-0.5">{event.meta}</p>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1 flex-shrink-0">
                    <span className={`material-symbols-outlined text-base ${statusInfo.cls}`}>
                      {statusInfo.icon}
                    </span>
                    <span className="text-[10px] text-on-surface-variant">{fmtRelative(event.timestamp)}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Pipelines */}
        <div className="bg-card rounded-2xl shadow-sm border border-border p-5 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-on-surface flex items-center gap-2">
              <span className="material-symbols-outlined text-primary text-lg">sync_alt</span>
              Pipelines
            </h2>
            <button className="text-xs font-semibold text-primary hover:underline">View all</button>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Platform</TableHead>
                <TableHead>Market</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Token</TableHead>
                <TableHead>Last Sync</TableHead>
                <TableHead>Success Rate</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pipelines.map((pl) => {
                const tb = tokenBadge(pl.tokenHealth, pl.tokenDaysLeft)
                return (
                  <TableRow key={pl.id}>
                    <TableCell className="font-medium text-on-surface">{pl.name}</TableCell>
                    <TableCell className="text-on-surface-variant">{pl.platform}</TableCell>
                    <TableCell className="text-on-surface-variant">{pl.market}</TableCell>
                    <TableCell>
                      <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${pipelineStatusBadge(pl.status)}`}>
                        {pl.status}
                      </span>
                    </TableCell>
                    <TableCell>
                      {tb ? (
                        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${tb.cls}`}>
                          {tb.label}
                        </span>
                      ) : (
                        <span className="material-symbols-outlined text-emerald-500 text-base">check_circle</span>
                      )}
                    </TableCell>
                    <TableCell className="text-on-surface-variant">{fmtTime(pl.lastSync)}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-border rounded-full h-1.5 w-16">
                          <div
                            className={`h-1.5 rounded-full ${pl.successRate >= 95 ? "bg-emerald-500" : pl.successRate >= 80 ? "bg-amber-400" : "bg-red-500"}`}
                            style={{ width: `${pl.successRate}%` }}
                          />
                        </div>
                        <span className="text-xs text-on-surface-variant">{pl.successRate}%</span>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </div>
      </>}

    </div>
  )
}
