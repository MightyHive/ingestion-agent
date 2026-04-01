import { create } from "zustand"
import type { Column } from "@/components/connectors/ColumnSelector"

interface ConnectorStore {
  // El conector que el usuario eligió
  connectorId: string | null
  connectorName: string | null

  // Session para el back
  sessionId: string | null

  // Campos que devolvió el agente
  fields: Column[]

  // Estado del agente mientras investiga
  isInvestigating: boolean
  investigationError: string | null
  completedNodes: string[]

  // Campos que el usuario seleccionó en /selectors
  selectedFields: string[]

  // Schema propuesto por el Data Architect
  schemaProposal: SchemaProposal | null
  isProposing: boolean
  proposalError: string | null

  // Actions
  setConnector: (id: string, name: string, sessionId: string) => void
  setInvestigating: (value: boolean) => void
  addCompletedNode: (node: string) => void
  setFields: (fields: Column[]) => void
  setInvestigationError: (error: string | null) => void
  setSelectedFields: (fields: string[]) => void
  setSchemaProposal: (proposal: SchemaProposal) => void
  setProposing: (value: boolean) => void
  setProposalError: (error: string | null) => void
  reset: () => void
}

export interface SchemaColumn {
  name: string        // nombre de la columna en BigQuery
  original: string    // nombre original en la API
  type: string        // FLOAT64, STRING, INT64, DATE, etc.
  mode: "NULLABLE" | "REQUIRED"
  description?: string
}

export interface SchemaProposal {
  tableName: string
  columns: SchemaColumn[]
  ddl: string
}

const initialState = {
  connectorId: null,
  connectorName: null,
  sessionId: null,
  fields: [],
  isInvestigating: false,
  investigationError: null,
  completedNodes: [],
  selectedFields: [],
  schemaProposal: null,
  isProposing: false,
  proposalError: null,
}

export const useConnectorStore = create<ConnectorStore>((set) => ({
  ...initialState,

  setConnector: (id, name, sessionId) =>
    set({ connectorId: id, connectorName: name, sessionId, completedNodes: [], fields: [], investigationError: null, schemaProposal: null }),

  setInvestigating: (value) => set({ isInvestigating: value }),

  addCompletedNode: (node) =>
    set((state) => ({ completedNodes: [...state.completedNodes, node] })),

  setFields: (fields) => set({ fields, isInvestigating: false }),

  setInvestigationError: (error) => set({ investigationError: error, isInvestigating: false }),

  setSelectedFields: (fields) => set({ selectedFields: fields }),

  setSchemaProposal: (proposal) => set({ schemaProposal: proposal, isProposing: false }),

  setProposing: (value) => set({ isProposing: value }),

  setProposalError: (error) => set({ proposalError: error, isProposing: false }),

  reset: () => set(initialState),
}))
