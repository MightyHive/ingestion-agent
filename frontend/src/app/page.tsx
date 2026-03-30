import {
  kpiMetrics,
  alerts,
  quickActions,
  pendingApprovals,
  recentActivity,
  agentTasks,
  pipelines,
  connectorHealth,
  type KpiStatus,
  type AlertSeverity,
  type ActivityStatus,
  type PipelineStatus,
  type ConnectorStatus,
  type AgentTaskStatus,
} from "@/lib/mock-data";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

// ── helpers ────────────────────────────────────────────────────────────────────

function kpiStatusColor(status: KpiStatus) {
  return {
    ok: "bg-emerald-500",
    warn: "bg-amber-400",
    error: "bg-red-500",
  }[status];
}

function alertBadgeClass(severity: AlertSeverity) {
  return {
    critical: "bg-red-100 text-red-700 border border-red-200",
    warning: "bg-amber-100 text-amber-700 border border-amber-200",
    info: "bg-blue-100 text-blue-700 border border-blue-200",
  }[severity];
}

function activityStatusIcon(status: ActivityStatus) {
  return {
    success: { icon: "check_circle", cls: "text-emerald-500" },
    failed: { icon: "cancel", cls: "text-red-500" },
    running: { icon: "sync", cls: "text-blue-500 animate-spin" },
    pending: { icon: "schedule", cls: "text-slate-400" },
  }[status];
}

function activityTypeIcon(type: string) {
  return (
    { sync: "sync_alt", deploy: "rocket_launch", schema: "schema", agent: "smart_toy" }[type] ??
    "circle"
  );
}

function pipelineStatusBadge(status: PipelineStatus) {
  return {
    active: "bg-emerald-100 text-emerald-700",
    syncing: "bg-blue-100 text-blue-700",
    paused: "bg-slate-100 text-slate-600",
    error: "bg-red-100 text-red-700",
  }[status];
}

function connectorStatusDot(status: ConnectorStatus) {
  return {
    healthy: "bg-emerald-500",
    degraded: "bg-amber-400",
    down: "bg-red-500",
  }[status];
}

function agentTaskBadge(status: AgentTaskStatus) {
  return {
    running: "bg-blue-100 text-blue-700",
    completed: "bg-emerald-100 text-emerald-700",
    needs_review: "bg-amber-100 text-amber-700",
  }[status];
}

function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
}

// ── page ───────────────────────────────────────────────────────────────────────

export default function Home() {
  const needsReview = agentTasks.filter((t) => t.status === "needs_review");
  const running = agentTasks.filter((t) => t.status === "running");
  const completed = agentTasks.filter((t) => t.status === "completed");

  return (
    <div className="space-y-6 max-w-[1400px]">

      {/* Page title */}
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">Dashboard</h1>
        <p className="text-sm text-on-surface-variant mt-0.5">Overview of your ingestion infrastructure</p>
      </div>

      {/* ── Row 1: KPI cards ── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-6 gap-4">
        {kpiMetrics.map((kpi) => (
          <div
            key={kpi.id}
            className="bg-card rounded-2xl p-4 shadow-sm border border-border flex flex-col gap-2"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-on-surface-variant truncate">{kpi.label}</span>
              <span className={`w-2 h-2 rounded-full flex-shrink-0 ${kpiStatusColor(kpi.status)}`} />
            </div>
            <div className="flex items-end gap-1">
              <span className="text-2xl font-bold text-on-surface leading-none">{kpi.value}</span>
              {kpi.unit && <span className="text-sm text-on-surface-variant mb-0.5">{kpi.unit}</span>}
            </div>
            {kpi.trend !== undefined && (
              <span
                className={`text-xs font-medium ${
                  kpi.trend > 0
                    ? "text-emerald-600"
                    : kpi.trend < 0
                    ? "text-red-500"
                    : "text-slate-400"
                }`}
              >
                {kpi.trend > 0 ? "▲" : kpi.trend < 0 ? "▼" : "—"}{" "}
                {Math.abs(kpi.trend)}
                {kpi.unit === "%" ? "pp" : ""}
              </span>
            )}
          </div>
        ))}
      </div>

      {/* ── Row 2: Needs Attention + Quick Actions ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* Needs Attention — 2/3 */}
        <div className="lg:col-span-2 bg-card rounded-2xl shadow-sm border border-border p-5 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-on-surface flex items-center gap-2">
              <span className="material-symbols-outlined text-amber-500 text-lg">warning</span>
              Needs Attention
            </h2>
            <span className="text-xs text-on-surface-variant">{alerts.length} items</span>
          </div>

          <div className="space-y-3">
            {alerts.map((alert) => (
              <div
                key={alert.id}
                className="flex items-start gap-3 p-3 rounded-xl bg-surface-container-low"
              >
                <span
                  className={`text-xs font-semibold px-2 py-0.5 rounded-full flex-shrink-0 mt-0.5 ${alertBadgeClass(alert.severity)}`}
                >
                  {alert.severity}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-on-surface-variant">{alert.source}</p>
                  <p className="text-sm text-on-surface mt-0.5">{alert.description}</p>
                  <p className="text-xs text-on-surface-variant mt-1">{fmtTime(alert.timestamp)}</p>
                </div>
                {alert.cta && (
                  <button className="flex-shrink-0 text-xs font-semibold text-primary hover:underline">
                    {alert.cta}
                  </button>
                )}
              </div>
            ))}
          </div>

          {/* Pending Approvals */}
          <div>
            <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-2">
              Pending Approvals
            </p>
            <div className="space-y-2">
              {pendingApprovals.map((pa) => (
                <div
                  key={pa.id}
                  className="flex items-center justify-between gap-2 p-2.5 rounded-lg border border-border bg-background"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="material-symbols-outlined text-base text-on-surface-variant">
                      {pa.type === "schema_change"
                        ? "schema"
                        : pa.type === "connector"
                        ? "hub"
                        : pa.type === "pipeline"
                        ? "sync_alt"
                        : "ads_click"}
                    </span>
                    <span className="text-sm text-on-surface truncate">{pa.description}</span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <span className="text-xs text-on-surface-variant">{fmtTime(pa.timestamp)}</span>
                    <button className="text-xs font-semibold text-primary hover:underline">Review</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Quick Actions — 1/3 */}
        <div className="bg-card rounded-2xl shadow-sm border border-border p-5 flex flex-col gap-4">
          <h2 className="font-semibold text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-lg">bolt</span>
            Quick Actions
          </h2>
          <div className="flex flex-col gap-2">
            {quickActions.map((qa) => (
              <button
                key={qa.id}
                className="flex items-center gap-3 px-4 py-3 rounded-xl border border-border bg-background hover:bg-surface-container-low transition-colors text-sm font-medium text-on-surface"
              >
                <span className="material-symbols-outlined text-primary text-lg">{qa.icon}</span>
                {qa.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* ── Row 3: Recent Activity + Agent Activity ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Recent Activity */}
        <div className="bg-card rounded-2xl shadow-sm border border-border p-5 flex flex-col gap-4">
          <h2 className="font-semibold text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-lg">history</span>
            Recent Activity
          </h2>
          <div className="space-y-2">
            {recentActivity.map((event) => {
              const { icon: statusIcon, cls } = activityStatusIcon(event.status);
              return (
                <div
                  key={event.id}
                  className="flex items-center gap-3 p-2.5 rounded-lg hover:bg-surface-container-low transition-colors"
                >
                  <span className="material-symbols-outlined text-base text-on-surface-variant">
                    {activityTypeIcon(event.type)}
                  </span>
                  <span className="flex-1 text-sm text-on-surface truncate">{event.title}</span>
                  <span className="text-xs text-on-surface-variant flex-shrink-0">{fmtTime(event.timestamp)}</span>
                  <span className={`material-symbols-outlined text-base flex-shrink-0 ${cls}`}>
                    {statusIcon}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Agent Activity */}
        <div className="bg-card rounded-2xl shadow-sm border border-border p-5 flex flex-col gap-4">
          <h2 className="font-semibold text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-lg">smart_toy</span>
            Agent Activity
          </h2>

          {/* Counters */}
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "Running", count: running.length, cls: "text-blue-600 bg-blue-50" },
              { label: "Completed", count: completed.length, cls: "text-emerald-600 bg-emerald-50" },
              { label: "Needs Review", count: needsReview.length, cls: "text-amber-600 bg-amber-50" },
            ].map(({ label, count, cls }) => (
              <div key={label} className={`rounded-xl p-3 text-center ${cls}`}>
                <p className="text-2xl font-bold">{count}</p>
                <p className="text-xs font-medium mt-0.5">{label}</p>
              </div>
            ))}
          </div>

          {/* Needs review list */}
          {needsReview.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-2">
                Needs Review
              </p>
              <div className="space-y-2">
                {needsReview.map((task) => (
                  <div
                    key={task.id}
                    className="flex items-center justify-between gap-2 p-2.5 rounded-lg border border-amber-200 bg-amber-50"
                  >
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-amber-700">{task.agent}</p>
                      <p className="text-sm text-on-surface truncate">{task.task}</p>
                    </div>
                    <button className="flex-shrink-0 text-xs font-semibold text-primary hover:underline">
                      Review
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* All tasks */}
          <div className="space-y-1.5">
            {agentTasks.map((task) => (
              <div
                key={task.id}
                className="flex items-center gap-3 px-2 py-1.5 rounded-lg hover:bg-surface-container-low transition-colors"
              >
                <span
                  className={`text-xs font-semibold px-2 py-0.5 rounded-full flex-shrink-0 ${agentTaskBadge(task.status)}`}
                >
                  {task.status.replace("_", " ")}
                </span>
                <span className="text-xs text-on-surface-variant flex-shrink-0">{task.agent}</span>
                <span className="text-sm text-on-surface truncate">{task.task}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Row 4: Pipelines table ── */}
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
              <TableHead>Last Sync</TableHead>
              <TableHead>Success Rate</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pipelines.map((pl) => (
              <TableRow key={pl.id}>
                <TableCell className="font-medium text-on-surface">{pl.name}</TableCell>
                <TableCell className="text-on-surface-variant">{pl.platform}</TableCell>
                <TableCell className="text-on-surface-variant">{pl.market}</TableCell>
                <TableCell>
                  <span
                    className={`text-xs font-semibold px-2 py-0.5 rounded-full ${pipelineStatusBadge(pl.status)}`}
                  >
                    {pl.status}
                  </span>
                </TableCell>
                <TableCell className="text-on-surface-variant">{fmtTime(pl.lastSync)}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 bg-border rounded-full h-1.5 w-16">
                      <div
                        className={`h-1.5 rounded-full ${
                          pl.successRate >= 95
                            ? "bg-emerald-500"
                            : pl.successRate >= 80
                            ? "bg-amber-400"
                            : "bg-red-500"
                        }`}
                        style={{ width: `${pl.successRate}%` }}
                      />
                    </div>
                    <span className="text-xs text-on-surface-variant">{pl.successRate}%</span>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* ── Row 5: Connector Health + Docs/Audit ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Connector Health */}
        <div className="bg-card rounded-2xl shadow-sm border border-border p-5 flex flex-col gap-4">
          <h2 className="font-semibold text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-lg">hub</span>
            Connector Health
          </h2>
          <div className="space-y-2">
            {connectorHealth.map((ch) => (
              <div
                key={ch.id}
                className="flex items-center justify-between p-3 rounded-xl bg-surface-container-low"
              >
                <div className="flex items-center gap-3">
                  <span className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${connectorStatusDot(ch.status)}`} />
                  <div>
                    <p className="text-sm font-medium text-on-surface">{ch.name}</p>
                    <p className="text-xs text-on-surface-variant">{ch.platform}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className={`text-xs font-semibold capitalize ${
                    ch.status === "healthy" ? "text-emerald-600" :
                    ch.status === "degraded" ? "text-amber-600" : "text-red-600"
                  }`}>
                    {ch.status}
                  </p>
                  <p className="text-xs text-on-surface-variant">
                    Checked {fmtTime(ch.lastCheck)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Docs / Audit */}
        <div className="bg-card rounded-2xl shadow-sm border border-border p-5 flex flex-col gap-4">
          <h2 className="font-semibold text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-lg">menu_book</span>
            Docs &amp; Audit
          </h2>
          <div className="space-y-2">
            {[
              { icon: "description", label: "Ingestion Architecture", sub: "Last updated Mar 28" },
              { icon: "policy", label: "Data Governance Policy", sub: "Last updated Mar 15" },
              { icon: "history_edu", label: "Audit Log — March 2026", sub: "387 events recorded" },
              { icon: "support_agent", label: "Agent Run History", sub: "42 runs this week" },
            ].map((item) => (
              <button
                key={item.label}
                className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-surface-container-low transition-colors text-left"
              >
                <span className="material-symbols-outlined text-primary text-lg">{item.icon}</span>
                <div>
                  <p className="text-sm font-medium text-on-surface">{item.label}</p>
                  <p className="text-xs text-on-surface-variant">{item.sub}</p>
                </div>
                <span className="material-symbols-outlined text-on-surface-variant text-base ml-auto">
                  chevron_right
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>

    </div>
  );
}
