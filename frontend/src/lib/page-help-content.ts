export interface PageHelpContent {
  title: string
  purpose: string
  steps: string[]
}

const helpByPath: Record<string, PageHelpContent> = {
  "/": {
    title: "Dashboard",
    purpose:
      "Your health and summary hub for the platform. Review credential expiry, failed pipelines, and nightly connection checks before taking action.",
    steps: [
      "Review the three KPI cards: expiring credentials, failed pipelines, and connection health ratio.",
      "Use Quick Actions to jump into Platform Credentials, Data Exploration, or Export Scheduler.",
      "Check the Connector Health Log for results from the nightly connection check at 2:00 AM UTC.",
      "Follow the onboarding guide to complete setup, or revisit any step when adding a new market.",
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
      "Define what to pull from each platform: choose a connector, credentials and reporting scope, select fields, then save a reusable extraction template.",
    steps: [
      "Step 1 — Select Connector: pick a platform connector to investigate available API fields.",
      "Browse Templates library below (step 1 only) to preview, edit, or delete saved templates.",
      "Step 2 — Credentials & Scope: choose credentials and the reporting level for your extract.",
      "Step 3 — Fields & Explore: select dimensions and metrics valid for your scope.",
      "Step 4 — Save Template: name the template and save it for use in Export Monitoring.",
      "Use Next and Back to move through the funnel; completed templates appear in Export Scheduler.",
    ],
  },
  "/destination-library": {
    title: "Data Destinations",
    purpose:
      "Register Google Cloud projects that receive exported data. Destinations link BigQuery or GCS to your extraction jobs.",
    steps: [
      "Click Add connection and provide project name, project ID, region, and service account.",
      "Run Test connection before saving to validate the GCP configuration.",
      "Review KPI cards for total destinations, healthy connections, and errors.",
      "Use row Test to re-validate; results appear on the Logs page.",
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
      "Review connection check results from Platform Credentials and Data Destinations in one place.",
    steps: [
      "Filter logs by date range, platform, or success/failure status.",
      "Each row shows when the check ran, the source name, platform, and outcome.",
      "Failed checks include the error message returned during validation.",
      "Run Test connection on a credential or destination to add a new log entry.",
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
