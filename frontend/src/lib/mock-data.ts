// ── KPIs ─────────────────────────────────────────────────────────────────────

export type KpiStatus = "ok" | "warn" | "error"

export interface KpiMetric {
  id: string
  label: string
  value: string | number
  unit?: string
  sub?: string        // secondary text below the value
  status: KpiStatus
  trend?: number
}

export const kpiMetrics: KpiMetric[] = [
  {
    id: "kpi-pipelines",
    label: "Active Pipelines",
    value: 4,
    status: "ok",
    trend: 1,
    sub: "1 with error",
  },
  {
    id: "kpi-last-sync",
    label: "Last Successful Sync",
    value: "3",
    unit: "min",
    status: "ok",
    sub: "Google Ads US",
  },
  {
    id: "kpi-tables",
    label: "BigQuery Tables",
    value: 7,
    status: "ok",
    sub: "2 created this week",
  },
  {
    id: "kpi-tokens",
    label: "Expiring Tokens",
    value: 2,
    status: "warn",
    sub: "Within 7 days",
  },
  {
    id: "kpi-connectors",
    label: "Healthy Connectors",
    value: "3/5",
    status: "warn",
    sub: "1 degraded · 1 down",
  },
]

// ── Needs Attention ───────────────────────────────────────────────────────────

export type AlertSeverity = "critical" | "warning" | "info"
export type AlertType = "token_expiry" | "sync_failure" | "schema_drift" | "rate_limit" | "info"

export interface Alert {
  id: string
  severity: AlertSeverity
  type: AlertType
  source: string
  description: string
  timestamp: string
  cta?: string
}

export const alerts: Alert[] = [
  {
    id: "alert-1",
    severity: "critical",
    type: "token_expiry",
    source: "Meta Ads — BR",
    description: "OAuth token expires in 2 days. Syncs will be paused automatically.",
    timestamp: "2026-03-30T08:00:00Z",
    cta: "Renew token",
  },
  {
    id: "alert-2",
    severity: "warning",
    type: "token_expiry",
    source: "TikTok Ads — MX",
    description: "OAuth token expires in 6 days.",
    timestamp: "2026-03-30T08:00:00Z",
    cta: "Renew token",
  },
  {
    id: "alert-3",
    severity: "critical",
    type: "sync_failure",
    source: "Meta Ads — BR",
    description: "Sync failed 3 times in a row. Last attempt 2h ago.",
    timestamp: "2026-03-30T06:00:00Z",
    cta: "View logs",
  },
  {
    id: "alert-4",
    severity: "warning",
    type: "schema_drift",
    source: "Google Ads — EU",
    description: "3 new fields detected in the API. Schema may be outdated.",
    timestamp: "2026-03-30T09:45:00Z",
    cta: "Review",
  },
  {
    id: "alert-5",
    severity: "info",
    type: "rate_limit",
    source: "TikTok Ads — MX",
    description: "Rate limit usage at 78%. Consider reducing sync frequency.",
    timestamp: "2026-03-30T09:00:00Z",
  },
]

// ── Recent Activity (agentes + pipeline + schema mezclados) ───────────────────

export type ActivityType = "sync" | "agent" | "schema" | "deploy" | "token"
export type ActivityStatus = "success" | "failed" | "running" | "pending"

export interface ActivityEvent {
  id: string
  type: ActivityType
  title: string
  timestamp: string
  status: ActivityStatus
  meta?: string    // info extra (plataforma, tabla, agente)
}

export const recentActivity: ActivityEvent[] = [
  {
    id: "ae-1",
    type: "sync",
    title: "Google Ads US — sync successful",
    timestamp: "2026-03-30T10:02:00Z",
    status: "success",
    meta: "1,847 records",
  },
  {
    id: "ae-2",
    type: "agent",
    title: "API Researcher investigated TikTok Ads API",
    timestamp: "2026-03-30T09:50:00Z",
    status: "success",
    meta: "48 fields discovered",
  },
  {
    id: "ae-3",
    type: "schema",
    title: "Table raw_tiktok_ads created in BigQuery",
    timestamp: "2026-03-30T09:45:00Z",
    status: "success",
    meta: "Data Architect",
  },
  {
    id: "ae-4",
    type: "sync",
    title: "Meta Ads BR — sync failed",
    timestamp: "2026-03-30T08:00:00Z",
    status: "failed",
    meta: "Expired token",
  },
  {
    id: "ae-5",
    type: "agent",
    title: "Coordinating Agent resolved schema conflict",
    timestamp: "2026-03-30T07:45:00Z",
    status: "success",
    meta: "Meta Ads BR",
  },
  {
    id: "ae-6",
    type: "schema",
    title: "Schema drift detected — Google Ads EU",
    timestamp: "2026-03-30T07:30:00Z",
    status: "pending",
    meta: "3 new fields",
  },
  {
    id: "ae-7",
    type: "deploy",
    title: "Selector v2.3 deployed to staging",
    timestamp: "2026-03-30T06:00:00Z",
    status: "success",
    meta: "Google Ads EU",
  },
]

// ── Pipelines ─────────────────────────────────────────────────────────────────

export type PipelineStatus = "active" | "paused" | "error" | "syncing"
export type TokenHealth = "ok" | "expiring" | "expired"

export interface Pipeline {
  id: string
  name: string
  platform: string
  market: string
  status: PipelineStatus
  lastSync: string
  successRate: number
  tokenHealth: TokenHealth
  tokenDaysLeft?: number
}
// coomentar para ver onboarding
export const pipelines: Pipeline[] = [
  // {
  //   id: "pl-1",
  //   name: "Google Ads Main",
  //   platform: "Google Ads",
  //   market: "US",
  //   status: "active",
  //   lastSync: "2026-03-30T10:02:00Z",
  //   successRate: 99,
  //   tokenHealth: "ok",
  // },
  // {
  //   id: "pl-2",
  //   name: "Meta Ads BR",
  //   platform: "Meta Ads",
  //   market: "BR",
  //   status: "error",
  //   lastSync: "2026-03-30T06:00:00Z",
  //   successRate: 72,
  //   tokenHealth: "expiring",
  //   tokenDaysLeft: 2,
  // },
  // {
  //   id: "pl-3",
  //   name: "TikTok MX",
  //   platform: "TikTok Ads",
  //   market: "MX",
  //   status: "paused",
  //   lastSync: "2026-03-29T22:00:00Z",
  //   successRate: 88,
  //   tokenHealth: "expiring",
  //   tokenDaysLeft: 6,
  // },
  // {
  //   id: "pl-4",
  //   name: "Google Ads EU",
  //   platform: "Google Ads",
  //   market: "EU",
  //   status: "active",
  //   lastSync: "2026-03-30T09:58:00Z",
  //   successRate: 97,
  //   tokenHealth: "ok",
  // },
  // {
  //   id: "pl-5",
  //   name: "Meta Ads US",
  //   platform: "Meta Ads",
  //   market: "US",
  //   status: "syncing",
  //   lastSync: "2026-03-30T09:30:00Z",
  //   successRate: 95,
  //   tokenHealth: "ok",
  // },
]

// ── Onboarding (para clientes sin pipelines) ──────────────────────────────────

export interface OnboardingStep {
  id: string
  label: string
  done: boolean
  href: string
}

export const onboardingSteps: OnboardingStep[] = [
  { id: "connector", label: "Connect an API", done: false, href: "/connectors" },
  { id: "selector",  label: "Select fields", done: false, href: "/selectors" },
  { id: "schema",    label: "Approve schema", done: false, href: "/schema" },
  { id: "scheduler", label: "Configure sync", done: false, href: "/scheduler" },
]

// ── Conector health (sidebar del dash) ───────────────────────────────────────

export type ConnectorStatus = "healthy" | "degraded" | "down"

export interface ConnectorHealth {
  id: string
  name: string
  platform: string
  status: ConnectorStatus
  lastCheck: string
  tokenHealth: TokenHealth
  tokenDaysLeft?: number
}

export const connectorHealth: ConnectorHealth[] = [
  { id: "ch-1", name: "Google Ads", platform: "Google Ads", status: "healthy", lastCheck: "2026-03-30T10:05:00Z", tokenHealth: "ok" },
  { id: "ch-2", name: "Meta Ads", platform: "Meta Ads", status: "degraded", lastCheck: "2026-03-30T10:05:00Z", tokenHealth: "expiring", tokenDaysLeft: 2 },
  { id: "ch-3", name: "TikTok Ads", platform: "TikTok Ads", status: "down", lastCheck: "2026-03-30T10:05:00Z", tokenHealth: "expiring", tokenDaysLeft: 6 },
  { id: "ch-4", name: "LinkedIn Ads", platform: "LinkedIn Ads", status: "healthy", lastCheck: "2026-03-30T10:05:00Z", tokenHealth: "ok" },
  { id: "ch-5", name: "DV360", platform: "Display & Video 360", status: "healthy", lastCheck: "2026-03-30T10:05:00Z", tokenHealth: "ok" },
]

// ── Quick actions ─────────────────────────────────────────────────────────────

export interface QuickAction {
  id: string
  label: string
  icon: string
  href: string
}

export const quickActions: QuickAction[] = [
  { id: "qa-1", label: "New connector", icon: "add_circle", href: "/connectors" },
  { id: "qa-2", label: "View selectors", icon: "ads_click", href: "/selectors" },
  { id: "qa-3", label: "Review schema", icon: "schema", href: "/schema" },
  { id: "qa-4", label: "Scheduler", icon: "calendar_today", href: "/scheduler" },
]
