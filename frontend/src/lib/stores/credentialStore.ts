import { create } from "zustand"
import {persist, createJSONStorage} from "zustand/middleware"

interface Credential {
    id: string
    name: string
    platform: string
    market: string
    brand: string,
    status?:string,
    owner?:string,
}

interface CredentialStore {
    credentials: Credential[]
    addCredential: (credential: Credential) => void
    updateCredential: (id:string, credential: Credential) => void
    deleteCredential: (id:string) => void
}

const DEFAULT_CREDENTIAL: Credential = {
    id: "meta_cadillac_france_10923412",
    name: "Meta France Cadillac",
    platform: "META",
    market: "France",
    brand: "Cadillac",
    status: "Healthy",
    owner: "J. Smith"
};

export const useCredentialStore = create<CredentialStore>()(persist((set) => ({
    credentials: [DEFAULT_CREDENTIAL],
    addCredential: (credential) => set((state) => ({credentials: [...state.credentials, credential]})),
    updateCredential: (id, credential) => set((state) => ({credentials: [...state.credentials.map(c => c.id === id ? credential : c)]})),
    deleteCredential: (id) => set((state) => ({credentials: state.credentials.filter(c => c.id !== id)})),
}), {
    name: "credentials-storage",
    storage: createJSONStorage(() => localStorage),
}))