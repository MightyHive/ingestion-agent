import { create } from "zustand"
import { persist, createJSONStorage } from "zustand/middleware"

export type DestinationConnectionStatus = "Healthy" | "Testing..." | "Failed" | "Action Needed"
export type DestinationLoadTarget = "BigQuery" | "GCS"

export interface SavedDestination {
  id: string
  name: string
  projectId: string
  region: string
  serviceAccount: string
  loadTarget: DestinationLoadTarget
  connectionStatus: DestinationConnectionStatus
}

const SEED_DESTINATIONS: SavedDestination[] = [
  {
    id: "seed-mds-prod-421",
    name: "MDS Production",
    projectId: "mds-prod-421",
    region: "us-east1",
    serviceAccount: "mds-agent@mds-prod-421.iam.gserviceaccount.com",
    loadTarget: "BigQuery",
    connectionStatus: "Healthy",
  },
  {
    id: "seed-cadillac",
    name: "Cadillac Analytics",
    projectId: "cadillac-gcp-01",
    region: "eu-west1",
    serviceAccount: "mds-agent@cadillac-gcp-01.iam.gserviceaccount.com",
    loadTarget: "BigQuery",
    connectionStatus: "Healthy",
  },
  {
    id: "seed-renault",
    name: "Renault Analytics",
    projectId: "renault-bq-prod",
    region: "eu-west1",
    serviceAccount: "mds-agent@renault-bq-prod.iam.gserviceaccount.com",
    loadTarget: "BigQuery",
    connectionStatus: "Action Needed",
  },
]

function migrateDestination(raw: Record<string, unknown>): SavedDestination | null {
  if (!raw.id || !raw.name || !raw.projectId) return null

  const legacyStatus = String(raw.status ?? "")
  let loadTarget: DestinationLoadTarget = "BigQuery"
  let connectionStatus: DestinationConnectionStatus = "Healthy"

  if (raw.loadTarget === "BigQuery" || raw.loadTarget === "GCS") {
    loadTarget = raw.loadTarget
  } else if (legacyStatus === "BigQuery" || legacyStatus === "GCS") {
    loadTarget = legacyStatus as DestinationLoadTarget
  }

  if (
    raw.connectionStatus === "Healthy" ||
    raw.connectionStatus === "Testing..." ||
    raw.connectionStatus === "Failed" ||
    raw.connectionStatus === "Action Needed"
  ) {
    connectionStatus = raw.connectionStatus
  } else if (legacyStatus === "Failed" || legacyStatus === "Action Needed") {
    connectionStatus = legacyStatus as DestinationConnectionStatus
  }

  return {
    id: String(raw.id),
    name: String(raw.name),
    projectId: String(raw.projectId),
    region: String(raw.region ?? "—"),
    serviceAccount: String(raw.serviceAccount ?? "—"),
    loadTarget,
    connectionStatus,
  }
}

interface DestinationStore {
  destinations: SavedDestination[]
  addDestination: (d: Omit<SavedDestination, "id">) => void
  updateDestination: (id: string, partial: Partial<SavedDestination>) => void
  deleteDestination: (id: string) => void
}

export const useDestinationStore = create<DestinationStore>()(
  persist(
    (set) => ({
      destinations: SEED_DESTINATIONS,
      addDestination: (d) =>
        set((s) => ({
          destinations: [...s.destinations, { ...d, id: crypto.randomUUID() }],
        })),
      updateDestination: (id, partial) =>
        set((s) => ({
          destinations: s.destinations.map((d) => (d.id === id ? { ...d, ...partial } : d)),
        })),
      deleteDestination: (id) =>
        set((s) => ({
          destinations: s.destinations.filter((d) => d.id !== id),
        })),
    }),
    {
      name: "destinations-storage",
      version: 2,
      storage: createJSONStorage(() =>
        typeof window !== "undefined"
          ? localStorage
          : { getItem: () => null, setItem: () => {}, removeItem: () => {} }
      ),
      migrate: (persisted: unknown) => {
        const state = persisted as { destinations?: unknown[] }
        if (!state?.destinations || !Array.isArray(state.destinations)) {
          return { destinations: SEED_DESTINATIONS }
        }
        const migrated = state.destinations
          .map((item) => migrateDestination(item as Record<string, unknown>))
          .filter((d): d is SavedDestination => d !== null)
        return { destinations: migrated.length > 0 ? migrated : SEED_DESTINATIONS }
      },
    }
  )
)

export function isHealthyDestinationStatus(status: DestinationConnectionStatus): boolean {
  return status === "Healthy"
}

export function isErrorDestinationStatus(status: DestinationConnectionStatus): boolean {
  return status === "Failed" || status === "Action Needed"
}
