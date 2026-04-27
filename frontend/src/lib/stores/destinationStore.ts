import { create } from "zustand"
import { persist, createJSONStorage } from "zustand/middleware"

export interface SavedDestination {
  id: string
  name: string
  projectId: string
  region: string
  serviceAccount: string
  status: string
}

const SEED_DESTINATIONS: SavedDestination[] = [
  {
    id: "seed-mds-prod-421",
    name: "MDS Production",
    projectId: "mds-prod-421",
    region: "us-east1",
    serviceAccount: "mds-agent@mds-prod-421.iam.gserviceaccount.com",
    status: "BigQuery",
  },
  {
    id: "seed-cadillac",
    name: "Cadillac Analytics",
    projectId: "cadillac-gcp-01",
    region: "eu-west1",
    serviceAccount: "mds-agent@cadillac-gcp-01.iam.gserviceaccount.com",
    status: "BigQuery",
  },
  {
    id: "seed-renault",
    name: "Renault Analytics",
    projectId: "renault-bq-prod",
    region: "eu-west1",
    serviceAccount: "mds-agent@renault-bq-prod.iam.gserviceaccount.com",
    status: "BigQuery",
  },
]

interface DestinationStore {
  destinations: SavedDestination[]
  addDestination: (d: Omit<SavedDestination, "id">) => void
  deleteDestination: (id: string) => void
}

export const useDestinationStore = create<DestinationStore>()(
  persist(
    (set) => ({
      destinations: SEED_DESTINATIONS,
      addDestination: (d) =>
        set((s) => ({
          destinations: [
            ...s.destinations,
            { ...d, id: crypto.randomUUID() },
          ],
        })),
      deleteDestination: (id) =>
        set((s) => ({
          destinations: s.destinations.filter((d) => d.id !== id),
        })),
    }),
    {
      name: "destinations-storage",
      storage: createJSONStorage(() =>
        typeof window !== "undefined"
          ? localStorage
          : { getItem: () => null, setItem: () => {}, removeItem: () => {} }
      ),
    }
  )
)
