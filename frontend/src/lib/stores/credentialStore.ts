import { create } from "zustand"
import { persist, createJSONStorage } from "zustand/middleware"

export interface Credential {
  id: string
  name: string
  platform: string
  market: string
  brand: string
  status?: string
  owner?: string
  token?: string
  tokenExpiresAt?: string
}

interface CredentialStore {
  credentials: Credential[]
  addCredential: (credential: Credential) => void
  updateCredential: (id: string, credential: Credential) => void
  deleteCredential: (id: string) => void
}

function daysFromNow(days: number) {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return date.toISOString()
}

const DEFAULT_CREDENTIALS: Credential[] = [
  {
    id: "meta_cadillac_france_10923412",
    name: "Meta France Cadillac",
    platform: "META",
    market: "France",
    brand: "Cadillac",
    status: "Healthy",
    owner: "J. Smith",
    tokenExpiresAt: daysFromNow(45),
  },
  {
    id: "google_ads_buick_france_88291003",
    name: "Google Ads France Buick",
    platform: "GOOGLE_ADS",
    market: "France",
    brand: "Buick",
    status: "Healthy",
    owner: "M. Chen",
    tokenExpiresAt: daysFromNow(60),
  },
  {
    id: "tiktok_mexico_chevrolet_44102981",
    name: "TikTok Mexico Chevrolet",
    platform: "TIKTOK",
    market: "Mexico",
    brand: "Chevrolet",
    status: "Action Needed",
    owner: "A. Rivera",
    tokenExpiresAt: daysFromNow(5),
  },
  {
    id: "meta_brazil_cadillac_77281904",
    name: "Meta Brazil Cadillac",
    platform: "META",
    market: "Brazil",
    brand: "Cadillac",
    status: "Broken",
    owner: "J. Smith",
    tokenExpiresAt: daysFromNow(-2),
  },
]

export const useCredentialStore = create<CredentialStore>()(
  persist(
    (set) => ({
      credentials: DEFAULT_CREDENTIALS,
      addCredential: (credential) =>
        set((state) => ({ credentials: [...state.credentials, credential] })),
      updateCredential: (id, credential) =>
        set((state) => ({
          credentials: state.credentials.map((c) => (c.id === id ? credential : c)),
        })),
      deleteCredential: (id) =>
        set((state) => ({ credentials: state.credentials.filter((c) => c.id !== id) })),
    }),
    {
      name: "credentials-storage",
      storage: createJSONStorage(() => localStorage),
    }
  )
)
