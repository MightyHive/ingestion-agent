import { create } from "zustand"
import { persist, createJSONStorage } from "zustand/middleware"

export type LogSourceType = "credential" | "destination"
export type LogStatus = "success" | "failure"

/** @deprecated Use LogStatus */
export type ConnectionHealthStatus = "healthy" | "degraded" | "failed"

export interface ConnectionHealthLogEntry {
  id: string
  sourceType: LogSourceType
  sourceId: string
  sourceName: string
  platform: string
  checkedAt: string
  status: LogStatus
  message: string
}

interface ConnectionHealthLogStore {
  logs: ConnectionHealthLogEntry[]
  addLog: (entry: Omit<ConnectionHealthLogEntry, "id">) => void
}

const NIGHTLY_CHECK_HOUR = 2

function nightlyTimestamp(daysAgo: number) {
  const date = new Date()
  date.setDate(date.getDate() - daysAgo)
  date.setHours(NIGHTLY_CHECK_HOUR, 0, 0, 0)
  return date.toISOString()
}

const DEFAULT_LOGS: ConnectionHealthLogEntry[] = [
  {
    id: "chl-1",
    sourceType: "credential",
    sourceId: "meta_cadillac_france_10923412",
    sourceName: "Meta France Cadillac",
    platform: "META",
    checkedAt: nightlyTimestamp(0),
    status: "success",
    message: "Token valid. API responded in 412ms.",
  },
  {
    id: "chl-2",
    sourceType: "credential",
    sourceId: "google_ads_buick_france_88291003",
    sourceName: "Google Ads France Buick",
    platform: "GOOGLE_ADS",
    checkedAt: nightlyTimestamp(0),
    status: "success",
    message: "OAuth refresh succeeded. Quota usage at 12%.",
  },
  {
    id: "chl-3",
    sourceType: "credential",
    sourceId: "tiktok_mexico_chevrolet_44102981",
    sourceName: "TikTok Mexico Chevrolet",
    platform: "TIKTOK",
    checkedAt: nightlyTimestamp(0),
    status: "failure",
    message: "Token expires in 5 days. Syncs will pause when expired.",
  },
  {
    id: "chl-4",
    sourceType: "credential",
    sourceId: "meta_brazil_cadillac_77281904",
    sourceName: "Meta Brazil Cadillac",
    platform: "META",
    checkedAt: nightlyTimestamp(1),
    status: "failure",
    message: "401 Unauthorized — token revoked or expired.",
  },
  {
    id: "chl-5",
    sourceType: "credential",
    sourceId: "meta_cadillac_france_10923412",
    sourceName: "Meta France Cadillac",
    platform: "META",
    checkedAt: nightlyTimestamp(1),
    status: "success",
    message: "Token valid. API responded in 389ms.",
  },
  {
    id: "chl-6",
    sourceType: "credential",
    sourceId: "google_ads_buick_france_88291003",
    sourceName: "Google Ads France Buick",
    platform: "GOOGLE_ADS",
    checkedAt: nightlyTimestamp(1),
    status: "success",
    message: "OAuth refresh succeeded. Quota usage at 11%.",
  },
  {
    id: "chl-7",
    sourceType: "destination",
    sourceId: "seed-mds-prod-421",
    sourceName: "MDS Production",
    platform: "GCP",
    checkedAt: nightlyTimestamp(0),
    status: "success",
    message: "BigQuery dataset reachable. Service account authorized.",
  },
  {
    id: "chl-8",
    sourceType: "destination",
    sourceId: "seed-renault",
    sourceName: "Renault Analytics",
    platform: "GCP",
    checkedAt: nightlyTimestamp(1),
    status: "failure",
    message: "403 Forbidden — service account missing BigQuery Data Editor role.",
  },
]

function migrateLegacyLog(raw: Record<string, unknown>): ConnectionHealthLogEntry | null {
  if (raw.sourceType && raw.sourceId && raw.sourceName) {
    const status = raw.status as string
    return {
      id: String(raw.id),
      sourceType: raw.sourceType as LogSourceType,
      sourceId: String(raw.sourceId),
      sourceName: String(raw.sourceName),
      platform: String(raw.platform),
      checkedAt: String(raw.checkedAt),
      status: status === "success" || status === "failure" ? status : status === "healthy" ? "success" : "failure",
      message: String(raw.message),
    }
  }

  if (raw.credentialId) {
    const legacyStatus = raw.status as ConnectionHealthStatus
    const status: LogStatus =
      legacyStatus === "healthy" ? "success" : legacyStatus === "failed" ? "failure" : "failure"
    return {
      id: String(raw.id),
      sourceType: "credential",
      sourceId: String(raw.credentialId),
      sourceName: String(raw.credentialName ?? raw.credentialId),
      platform: String(raw.platform),
      checkedAt: String(raw.checkedAt),
      status,
      message: String(raw.message),
    }
  }

  return null
}

export function appendConnectionLog(entry: Omit<ConnectionHealthLogEntry, "id" | "checkedAt"> & { checkedAt?: string }) {
  useConnectionHealthLogStore.getState().addLog({
    ...entry,
    checkedAt: entry.checkedAt ?? new Date().toISOString(),
  })
}

export const useConnectionHealthLogStore = create<ConnectionHealthLogStore>()(
  persist(
    (set) => ({
      logs: DEFAULT_LOGS,
      addLog: (entry) =>
        set((state) => ({
          logs: [{ ...entry, id: crypto.randomUUID() }, ...state.logs],
        })),
    }),
    {
      name: "connection-health-log-storage",
      version: 2,
      storage: createJSONStorage(() =>
        typeof window !== "undefined"
          ? localStorage
          : { getItem: () => null, setItem: () => {}, removeItem: () => {} }
      ),
      migrate: (persisted: unknown) => {
        const state = persisted as { logs?: unknown[] }
        if (!state?.logs || !Array.isArray(state.logs)) {
          return { logs: DEFAULT_LOGS }
        }
        const migrated = state.logs
          .map((item) => migrateLegacyLog(item as Record<string, unknown>))
          .filter((e): e is ConnectionHealthLogEntry => e !== null)
        return { logs: migrated.length > 0 ? migrated : DEFAULT_LOGS }
      },
    }
  )
)

export function isNightlyCheckEntry(checkedAt: string) {
  const date = new Date(checkedAt)
  return date.getHours() === NIGHTLY_CHECK_HOUR && date.getMinutes() === 0
}
