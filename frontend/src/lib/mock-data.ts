export type KpiStatus = "ok" | "warn" | "error";

export interface KpiMetric {
  id: string;
  label: string;
  value: string | number;
  unit?: string;
  trend?: number; // positive = up, negative = down
  status: KpiStatus;
}

export type AlertSeverity = "critical" | "warning" | "info";

export interface Alert {
  id: string;
  severity: AlertSeverity;
  source: string;
  description: string;
  timestamp: string;
  cta?: string;
}

export interface QuickAction {
  id: string;
  label: string;
  icon: string;
}

export type ApprovalType = "schema_change" | "connector" | "pipeline" | "selector";

export interface PendingApproval {
  id: string;
  description: string;
  type: ApprovalType;
  timestamp: string;
}

export type ActivityType = "sync" | "deploy" | "schema" | "agent";
export type ActivityStatus = "success" | "failed" | "running" | "pending";

export interface ActivityEvent {
  id: string;
  type: ActivityType;
  title: string;
  timestamp: string;
  status: ActivityStatus;
}

export type AgentTaskStatus = "running" | "completed" | "needs_review";

export interface AgentTask {
  id: string;
  agent: string;
  task: string;
  status: AgentTaskStatus;
}

export type PipelineStatus = "active" | "paused" | "error" | "syncing";

export interface Pipeline {
  id: string;
  name: string;
  platform: string;
  market: string;
  status: PipelineStatus;
  lastSync: string;
  successRate: number;
}

export type ConnectorStatus = "healthy" | "degraded" | "down";

export interface ConnectorHealth {
  id: string;
  name: string;
  platform: string;
  status: ConnectorStatus;
  lastCheck: string;
}

// --- Mock data instances ---

export const kpiMetrics: KpiMetric[] = [
  { id: "kpi-1", label: "Active Pipelines", value: 24, status: "ok", trend: 2 },
  { id: "kpi-2", label: "Syncs Today", value: 1847, status: "ok", trend: 12 },
  { id: "kpi-3", label: "Avg Latency", value: "1.2", unit: "s", status: "warn", trend: -5 },
  { id: "kpi-4", label: "Error Rate", value: "0.8", unit: "%", status: "ok", trend: -1 },
  { id: "kpi-5", label: "Pending Approvals", value: 3, status: "warn", trend: 3 },
  { id: "kpi-6", label: "Connector Health", value: "92", unit: "%", status: "ok", trend: 0 },
];

export const alerts: Alert[] = [
  {
    id: "alert-1",
    severity: "critical",
    source: "Google Ads — US",
    description: "API token expired. Sync has been paused for 6 hours.",
    timestamp: "2026-03-30T08:14:00Z",
    cta: "Reconnect",
  },
  {
    id: "alert-2",
    severity: "warning",
    source: "Meta Ads — BR",
    description: "Schema drift detected in `campaigns` table. 2 new fields.",
    timestamp: "2026-03-30T09:45:00Z",
    cta: "Review",
  },
  {
    id: "alert-3",
    severity: "info",
    source: "Scheduler",
    description: "Nightly batch job completed with 3 retries.",
    timestamp: "2026-03-30T03:00:00Z",
  },
];

export const quickActions: QuickAction[] = [
  { id: "qa-1", label: "Add Connector", icon: "add_circle" },
  { id: "qa-2", label: "Run Sync", icon: "sync" },
  { id: "qa-3", label: "Review Schema", icon: "schema" },
  { id: "qa-4", label: "New Selector", icon: "ads_click" },
  { id: "qa-5", label: "View Logs", icon: "terminal" },
];

export const pendingApprovals: PendingApproval[] = [
  {
    id: "pa-1",
    description: "New field `ad_set_budget_remaining` in Meta Ads campaigns",
    type: "schema_change",
    timestamp: "2026-03-30T07:30:00Z",
  },
  {
    id: "pa-2",
    description: "TikTok Ads connector — MX market",
    type: "connector",
    timestamp: "2026-03-29T18:00:00Z",
  },
  {
    id: "pa-3",
    description: "Updated ROAS selector logic for Google Ads — EU",
    type: "selector",
    timestamp: "2026-03-29T15:20:00Z",
  },
];

export const recentActivity: ActivityEvent[] = [
  {
    id: "ae-1",
    type: "sync",
    title: "Google Ads — US synced successfully",
    timestamp: "2026-03-30T10:02:00Z",
    status: "success",
  },
  {
    id: "ae-2",
    type: "schema",
    title: "Schema migration applied — Meta Ads BR",
    timestamp: "2026-03-30T09:50:00Z",
    status: "success",
  },
  {
    id: "ae-3",
    type: "sync",
    title: "TikTok Ads — MX sync failed",
    timestamp: "2026-03-30T09:35:00Z",
    status: "failed",
  },
  {
    id: "ae-4",
    type: "deploy",
    title: "Selector v2.3 deployed to staging",
    timestamp: "2026-03-30T08:00:00Z",
    status: "success",
  },
  {
    id: "ae-5",
    type: "agent",
    title: "Coordinating Agent resolved connector issue",
    timestamp: "2026-03-30T07:45:00Z",
    status: "success",
  },
];

export const agentTasks: AgentTask[] = [
  { id: "at-1", agent: "Coordinating Agent", task: "Orchestrating TikTok Ads — MX pipeline setup", status: "running" },
  { id: "at-2", agent: "API Researcher Agent", task: "Read TikTok Ads API v2 documentation", status: "completed" },
  { id: "at-3", agent: "Data Architect Agent", task: "Propose BigQuery schema for TikTok Ads", status: "needs_review" },
  { id: "at-4", agent: "Software Engineer Agent", task: "Write Cloud Function for Meta Ads BR", status: "completed" },
  { id: "at-5", agent: "QA & Security Agent", task: "Audit Meta Ads BR connector code", status: "needs_review" },
  { id: "at-6", agent: "DevOps Agent", task: "Deploy Google Ads EU Cloud Function", status: "completed" },
];

export const pipelines: Pipeline[] = [
  { id: "pl-1", name: "Google Ads Main", platform: "Google Ads", market: "US", status: "active", lastSync: "2026-03-30T10:02:00Z", successRate: 99 },
  { id: "pl-2", name: "Meta Ads BR", platform: "Meta Ads", market: "BR", status: "error", lastSync: "2026-03-30T04:00:00Z", successRate: 72 },
  { id: "pl-3", name: "TikTok MX", platform: "TikTok Ads", market: "MX", status: "paused", lastSync: "2026-03-29T22:00:00Z", successRate: 88 },
  { id: "pl-4", name: "Google Ads EU", platform: "Google Ads", market: "EU", status: "active", lastSync: "2026-03-30T09:58:00Z", successRate: 97 },
  { id: "pl-5", name: "Meta Ads US", platform: "Meta Ads", market: "US", status: "syncing", lastSync: "2026-03-30T09:30:00Z", successRate: 95 },
];

export const connectorHealth: ConnectorHealth[] = [
  { id: "ch-1", name: "Google Ads", platform: "Google Ads", status: "healthy", lastCheck: "2026-03-30T10:05:00Z" },
  { id: "ch-2", name: "Meta Ads", platform: "Meta Ads", status: "degraded", lastCheck: "2026-03-30T10:05:00Z" },
  { id: "ch-3", name: "TikTok Ads", platform: "TikTok Ads", status: "down", lastCheck: "2026-03-30T10:05:00Z" },
  { id: "ch-4", name: "LinkedIn Ads", platform: "LinkedIn Ads", status: "healthy", lastCheck: "2026-03-30T10:05:00Z" },
  { id: "ch-5", name: "DV360", platform: "Display & Video 360", status: "healthy", lastCheck: "2026-03-30T10:05:00Z" },
];
