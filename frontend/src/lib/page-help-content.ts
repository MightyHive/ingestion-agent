export interface PageHelpContent {
  title: string
  purpose: string
  steps: string[]
}

const helpByPath: Record<string, PageHelpContent> = {
  "/": {
    title: "Dashboard",
    purpose:
      "Your home view for pipeline health, recent activity, and quick actions. Use it to spot issues early and jump into the right workflow.",
    steps: [
      "Review KPI cards and alerts in Needs Attention to see what requires action.",
      "Check Recent Activity for the latest syncs, failures, and configuration changes.",
      "Use Quick Actions or onboarding steps to open Platform Credentials, Data Exploration, or Export Monitoring.",
      "Monitor connector health before scheduling or re-running exports.",
    ],
  },
  "/credentials-library": {
    title: "Platform Credentials",
    purpose:
      "Store and manage authentication for each advertising or analytics platform. Credentials are reused across templates and scheduled exports.",
    steps: [
      "Click Add Connection and enter a name, platform, market, and brand.",
      "Paste a valid access token (or connect via your platform’s OAuth flow when available).",
      "Save the connection and confirm it appears as healthy in the list.",
      "Filter by platform to find credentials quickly before building extractions.",
      "Return here whenever a token expires or you onboard a new market.",
    ],
  },
  "/data-connection": {
    title: "Data Exploration",
    purpose:
      "Define what to pull from each platform: choose a connector, select fields and report level, then save a reusable extraction template.",
    steps: [
      "Step 1 — Connection: pick a platform connector to investigate available API fields.",
      "Browse Templates library below (step 1 only) to preview, edit, or delete saved templates.",
      "Step 2 — Selectors: choose dimensions, metrics, and the report level for your extract.",
      "Step 3 — Template: name the template and save it for use in Export Monitoring.",
      "Use Next and Back to move through the wizard; completed templates appear in Export Scheduler.",
    ],
  },
  "/destination-library": {
    title: "Data Destinations",
    purpose:
      "Register Google Cloud projects that receive exported data. Destinations link BigQuery (or other targets) to your extraction jobs.",
    steps: [
      "Click Add destination and provide project name, project ID, and region.",
      "Enter the service account email that will write to the destination dataset.",
      "Save and verify the destination shows an active status.",
      "Select this destination when configuring exports in Export Monitoring.",
    ],
  },
  "/export-planner": {
    title: "Export Scheduler",
    purpose:
      "View and manage scheduled exports: trigger on-demand runs, backfill historical data, or adjust existing schedules.",
    steps: [
      "Review Your scheduled exports for frequency, last run, and next run.",
      "Use Run now to trigger an immediate sync for a job.",
      "Use Backfill to load historical data for a chosen date range.",
      "Click Edit to change schedule, credentials, or destination tables.",
      "Create new schedules from Export Monitoring when none exist yet.",
    ],
  },
  "/data-export": {
    title: "Export Monitoring",
    purpose:
      "Configure end-to-end exports: pick a destination, bind a template and credentials, then set how often data should refresh.",
    steps: [
      "Step 1 — Destinations: choose the GCP project that will receive the data.",
      "Step 2 — Create Extraction: select platform, template, credentials, and per-credential table names.",
      "Step 3 — Scheduler: set frequency, time (UTC), and refresh window, then save the job.",
      "Saved jobs appear in Export Scheduler for monitoring and manual runs.",
      "Return here to add exports for additional markets or platforms.",
    ],
  },
  "/logs": {
    title: "Logs",
    purpose:
      "Audit trail for pipeline and export activity. Use logs to troubleshoot failures and confirm successful runs.",
    steps: [
      "Filter by date, job, or severity when log streaming is enabled.",
      "Open a run to see step-by-step agent and API messages.",
      "Correlate errors here with alerts on the Dashboard.",
      "Share log excerpts with your team when escalating platform or permission issues.",
    ],
  },
}

const defaultHelp: PageHelpContent = {
  title: "Help",
  purpose: "Contextual guidance for the page you are viewing.",
  steps: [
    "Select a section from the sidebar to open a feature area.",
    "Use the help button on any page to learn its purpose and recommended workflow.",
  ],
}

export function getPageHelp(pathname: string): PageHelpContent {
  if (helpByPath[pathname]) return helpByPath[pathname]

  const match = Object.keys(helpByPath)
    .filter((path) => path !== "/")
    .sort((a, b) => b.length - a.length)
    .find((path) => pathname.startsWith(path))

  return match ? helpByPath[match] : defaultHelp
}
