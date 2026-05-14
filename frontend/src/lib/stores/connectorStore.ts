import { create } from "zustand"
import type { FieldRow, FieldType } from "@/lib/platforms/types"
import { columnsFromUiTriggerData } from "@/lib/ui-trigger-fields"
import { mockAgentStream, mockSubmitInputStream } from "@/lib/mock-agent"
import { getConnectorSessionId } from "@/lib/sessions"


const IS_MOCK = process.env.NEXT_PUBLIC_MOCK === "true"
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

// --- Tipos de Soporte ---

export interface ChatMessage {
  type: string
  content: string
}

export type UiTriggerState = {
  component: string
  message?: string
  data?: Record<string, unknown>
} | null

export interface TemplateColumn {
  name: string
  original: string
  type: string
  mode: "NULLABLE" | "REQUIRED"
  description?: string
}

export interface ScheduleConfig {
  frequency: "hourly" | "daily" | "weekly" | "monthly"
  time: string
  isReady: boolean
}

export interface TemplateProposal {
  tableName: string
  columns: TemplateColumn[]
  ddl: string
}

export interface CatalogConnector {
  id: string
  name: string
  platform: string
  connector: string
  version: string
  status: "alpha" | "beta" | "stable" | "deprecated"
  owner?: string
  description?: string
  available_fields_count: number
  params_summary: {
    required: string[]
    optional: string[]
    one_of: string[][]
  }
}

// Un field dentro del manifest (GET /api/catalog/{id})
export interface ManifestField {
  name: string
  type: string
  mode?: "NULLABLE" | "REQUIRED" | "REPEATED"
  description?: string
  selectable?: boolean
  items_type?: string
  fields?: string[]
}

// Un parámetro del manifest
export interface ManifestParam {
  name: string
  type: string
  days_back?: number
  date_start?: string
  date_stop?: string
  since?: string
  until?: string
  description?: string
}

// El manifest completo (solo lo que usa el frontend)
export interface Manifest {
  id: string
  name: string
  platform: string
  params: {
    required: ManifestParam[]
    optional: ManifestParam[]
    one_of: string[][]
  }
  available_fields: ManifestField[]
  table_naming: { bronze_pattern: string }
}

// Respuesta exitosa de POST /api/run
export interface RunResult {
  manifest_id: string
  target_table: string
  ddl: string
  columns: string[]
  row_count: number
  rows_preview: Record<string, unknown>[]
  errors: string[]
  requestId?: string
}

// --- Helpers de Utilidad ---

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null
}

function dedupeByStableKey<T>(items: readonly T[], keyOf: (item: T) => string): T[] {
  const seen = new Set<string>()
  const out: T[] = []
  for (const item of items) {
    const key = keyOf(item)
    if (seen.has(key)) continue
    seen.add(key)
    out.push(item)
  }
  return out
}

function dedupeColumnsByDomainId(columns: FieldRow[]): FieldRow[] {
  return dedupeByStableKey(columns, (c) => c.id)
}

function dedupeFieldIdList(ids: string[]): string[] {
  return dedupeByStableKey(ids, (s) => s)
}

function dedupeTemplateColumnsByFieldName(columns: TemplateColumn[]): TemplateColumn[] {
  return dedupeByStableKey(columns, (c) => c.name)
}

function feedSseBuffer(buffer: string, chunk: string): { buffer: string; events: unknown[] } {
  buffer += chunk
  const events: unknown[] = []
  const parts = buffer.split("\n\n")
  const rest = parts.pop() ?? ""
  for (const part of parts) {
    const line = part.replace(/^data:\s*/i, "").trim()
    if (!line) continue
    try {
      events.push(JSON.parse(line))
    } catch { /* malformed SSE chunk — skip */ }
  }
  return { buffer: rest, events }
}

// Convierte tipo BigQuery del manifest → FieldType del ColumnSelector
function bigqueryTypeToFieldType(t: string): FieldType {
  if (t === "INT64" || t === "INTEGER") return "INTEGER"
  if (t === "FLOAT64" || t === "NUMERIC" || t === "BIGNUMERIC") return "FLOAT"
  if (t === "BOOL" || t === "BOOLEAN") return "BOOLEAN"
  if (t === "DATE" || t === "DATETIME" || t === "TIMESTAMP" || t === "TIME") return "DATE"
  return "STRING" // STRING, JSON, BYTES, ARRAY, STRUCT → opaque
}

// Convierte available_fields del manifest → FieldRow[] para el ColumnSelector
function manifestFieldsToFieldRows(manifest: Manifest): FieldRow[] {
  return manifest.available_fields
    .filter((f) => f.selectable !== false)
    .map((f) => ({
      id: f.name,
      name: f.name,
      type: bigqueryTypeToFieldType(f.type),
      kind: "metric" as const,  // el manifest no distingue metric/dimension por ahora
      endpoint: manifest.id,
      description: f.description,
    }))
}


// --- Definición del Store ---

interface ConnectorStore {
  connectorId: string | null
  connectorName: string | null
  sessionId: string | null
  fields: FieldRow[]
  isInvestigating: boolean
  investigationError: string | null
  completedNodes: string[]
  selectedFields: string[]
  templateProposal: TemplateProposal | null
  isProposing: boolean
  proposalError: string | null
  messages: ChatMessage[]
  uiTrigger: UiTriggerState
  abortController: AbortController | null
  
  // Scheduler State
  scheduleConfig: ScheduleConfig | null

  // real API
  catalogConnectors: CatalogConnector[]
  isLoadingCatalog: boolean
  catalogError: string | null
  manifest: Manifest | null
  params: Record<string, unknown>  // valores del form de parámetros (days_back, etc.)
  isRunning: boolean
  runError: string | null
  runRequestId: string | null      // para mostrar en mensajes de error
  runResult: RunResult | null

  // Actions
  setConnector: (id: string, name: string, sessionId: string) => void
  setInvestigating: (value: boolean) => void
  addCompletedNode: (node: string) => void
  setFields: (fields: FieldRow[]) => void
  setInvestigationError: (error: string | null) => void
  setSelectedFields: (fields: string[]) => void
  setTemplateProposal: (proposal: TemplateProposal) => void
  setProposing: (value: boolean) => void
  setProposalError: (error: string | null) => void
  startInvestigation: (sessionId: string, message: string) => Promise<void>
  submitUserInput: (sessionId: string, userInput: unknown) => Promise<void>
  abortStream: () => void
  setScheduleConfig: (config: Partial<ScheduleConfig>) => void
  reset: () => void
  loadCatalog: () => Promise<void>
  selectConnector: (id: string, name: string) => Promise<void>
  setParam: (key: string, value: unknown) => void
  runPipeline: () => Promise<void>
}

function TemplateColumnsFromUiTrigger(raw: unknown): TemplateColumn[] {
  if (!Array.isArray(raw)) return []
  const mapped = raw.map((item): TemplateColumn => {
    if (!isRecord(item)) return { name: "", original: "", type: "STRING", mode: "NULLABLE" }
    const fieldName = typeof item.field_name === "string" ? item.field_name : typeof item.name === "string" ? item.name : ""
    return {
      name: fieldName,
      original: typeof item.original === "string" ? item.original : fieldName,
      type: typeof item.type === "string" ? item.type : "STRING",
      mode: item.mode === "REQUIRED" ? "REQUIRED" : "NULLABLE",
      description: typeof item.description === "string" ? item.description : undefined,
    }
  })
  return dedupeTemplateColumnsByFieldName(mapped)
}

const initialState = {
  connectorId: null,
  connectorName: null,
  sessionId: null,
  fields: [] as FieldRow[],
  isInvestigating: false,
  investigationError: null,
  completedNodes: [] as string[],
  selectedFields: [] as string[],
  templateProposal: null,
  isProposing: false,
  proposalError: null,
  messages: [] as ChatMessage[],
  uiTrigger: null as UiTriggerState,
  abortController: null as AbortController | null,
  scheduleConfig: null,

  // real API
  catalogConnectors: [] as CatalogConnector[],
  isLoadingCatalog: false,
  catalogError: null,
  manifest: null,
  params: {} as Record<string, unknown>,
  isRunning: false,
  runError: null,
  runRequestId: null,
  runResult: null,
}

export const useConnectorStore = create<ConnectorStore>()((set, get) => ({
  ...initialState,

  setConnector: (id, name, sessionId) => {
    const ac = get().abortController
    if (ac) ac.abort()
    set({
      connectorId: id,
      connectorName: name,
      sessionId,
      completedNodes: [],
      fields: [],
      investigationError: null,
      templateProposal: null,
      messages: [],
      uiTrigger: null,
      abortController: null,
      isInvestigating: false,
    })
  },

  setInvestigating: (value) => set({ isInvestigating: value }),

  addCompletedNode: (node) =>
    set((state) => ({ completedNodes: [...state.completedNodes, node] })),

  setFields: (fields) => set({ fields: dedupeColumnsByDomainId(fields), isInvestigating: false }),

  setInvestigationError: (error) => set({ investigationError: error, isInvestigating: false }),

  setSelectedFields: (fields) => set({ selectedFields: dedupeFieldIdList(fields) }),

  setTemplateProposal: (proposal) =>
    set({
      templateProposal: {
        ...proposal,
        columns: dedupeTemplateColumnsByFieldName(proposal.columns),
      },
      isProposing: false,
    }),

  setProposing: (value) => set({ isProposing: value }),

  setProposalError: (error) => set({ proposalError: error, isProposing: false }),

  // --- Lógica del Scheduler ---
  setScheduleConfig: (config) => 
    set((state) => ({
      scheduleConfig: state.scheduleConfig 
        ? { ...state.scheduleConfig, ...config } 
        : { frequency: "daily", time: "00:00", isReady: false, ...config } as ScheduleConfig
    })),

  abortStream: () => {
    const ac = get().abortController
    if (ac) ac.abort()
    set({ abortController: null, isInvestigating: false, isProposing: false })
  },

  // SSE API
  loadCatalog: async () => {
    if (IS_MOCK) return  // en mock el catálogo es el array hardcodeado de ConnectionStep
    set({ isLoadingCatalog: true, catalogError: null })
    try {
      const res = await fetch(`${API_BASE}/api/catalog`)
      if (!res.ok) throw new Error(`GET /api/catalog → ${res.status}`)
      const data = await res.json()
      set({ catalogConnectors: data.connectors ?? [], isLoadingCatalog: false })
    } catch (e) {
      set({ catalogError: e instanceof Error ? e.message : "Error cargando catálogo", isLoadingCatalog: false })
    }
  },

  selectConnector: async (id, name) => {
    if (IS_MOCK) {
      // Path mock: igual que antes
      const sessionId = getConnectorSessionId(id)
      get().setConnector(id, name, sessionId)
      await get().startInvestigation(sessionId, "Mock query")
    } else {
      // Path real: fetch manifest + mapea fields
      set({
        connectorId: id,
        connectorName: name,
        manifest: null,
        fields: [],
        selectedFields: [],
        templateProposal: null,
        runResult: null,
        runError: null,
        params: {},
        isInvestigating: true,       // reusamos el spinner que ya existe en SelectionStep
        investigationError: null,
      })
      try {
        const res = await fetch(`${API_BASE}/api/catalog/${id}`)
        if (!res.ok) throw new Error(`GET /api/catalog/${id} → ${res.status}`)
        const manifest: Manifest = await res.json()
        set({ manifest, fields: manifestFieldsToFieldRows(manifest), isInvestigating: false })
      } catch (e) {
        set({
          investigationError: e instanceof Error ? e.message : "Error cargando el conector",
          isInvestigating: false,
        })
      }
    }
  },

  setParam: (key, value) =>
    set((state) => ({ params: { ...state.params, [key]: value } })),

  runPipeline: async () => {
    const { connectorId, selectedFields, sessionId, params } = get()
    if (!connectorId) return

    if (IS_MOCK) {
      // Path mock: submitUserInput con SSE, igual que antes
      await get().submitUserInput(sessionId!, { columns_selected: selectedFields })
    } else {
      // Path real: POST /api/run
      set({ isRunning: true, runError: null, runRequestId: null })
      try {
        const res = await fetch(`${API_BASE}/api/run`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            manifest_id: connectorId,
            params: { fields: selectedFields, ...params },
          }),
        })
        const requestId = res.headers.get("X-Request-Id") ?? null
        const body = await res.json()
        if (!res.ok) {
          set({ runError: body.reason ?? `Error ${res.status}`, runRequestId: requestId, isRunning: false })
          return
        }
        const result: RunResult = { ...body, requestId }
        set({
          runResult: result,
          templateProposal: {
            tableName: result.target_table,
            ddl: result.ddl,
            columns: result.columns.map((colName) => ({
              name: colName,
              original: colName,
              type: "STRING",
              mode: "NULLABLE" as const,
            })),
          },
          isRunning: false,
        })
      } catch (e) {
        set({ runError: e instanceof Error ? e.message : "Error ejecutando el pipeline", isRunning: false })
      }
    }
  },

  startInvestigation: async (sessionId, message) => {
    const prev = get().abortController
    if (prev) prev.abort()

    const ac = new AbortController()
    set((state) => ({
      isInvestigating: true,
      investigationError: null,
      uiTrigger: null,
      abortController: ac,
      completedNodes: [],
      messages: [...state.messages, { type: "user", content: message }],
    }))

    const applySseEvents = (events: unknown[]) => {
      for (const raw of events) {
        if (!isRecord(raw)) continue
        const type = raw.type
        if (type === "progress" && typeof raw.node === "string") {
          set((state) => ({ completedNodes: [...state.completedNodes, raw.node as string] }))
        } else if (type === "final") {
          const responseText = typeof raw.response_text === "string" ? raw.response_text : ""
          const utRaw = raw.ui_trigger
          set((state) => {
            const uiTrigger: UiTriggerState = isRecord(utRaw)
              ? {
                  component: String(utRaw.component ?? ""),
                  message: typeof utRaw.message === "string" ? utRaw.message : undefined,
                  data: isRecord(utRaw.data) ? utRaw.data : undefined,
                }
              : null
            let fields = state.fields
            if (isRecord(utRaw) && utRaw.component === "ColumnSelector" && isRecord(utRaw.data)) {
              const platformId = state.connectorId ?? "meta"
              const mapped = columnsFromUiTriggerData(utRaw.data, platformId)
              if (mapped.length) fields = dedupeColumnsByDomainId(mapped)
            }
            return {
              isInvestigating: false,
              abortController: null,
              uiTrigger,
              fields,
              messages: [...state.messages, { type: "assistant", content: responseText }],
            }
          })
        }
      }
    }

    try {
      if (IS_MOCK) {
        const connectorId = get().connectorId ?? "meta"
        let buf = ""
        for await (const sseChunk of mockAgentStream(connectorId)) {
          if (ac.signal.aborted) break
          const { buffer, events } = feedSseBuffer(buf, sseChunk)
          buf = buffer
          applySseEvents(events)
        }
      } else {
        const response = await fetch(`${API_BASE}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, message }),
          signal: ac.signal,
        })
        if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`)
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ""
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const { buffer: nextBuf, events } = feedSseBuffer(buffer, decoder.decode(value, { stream: true }))
          buffer = nextBuf
          applySseEvents(events)
        }
      }
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") {
        set({ isInvestigating: false, abortController: null })
        return
      }
      set({
        investigationError: e instanceof Error ? e.message : "Failed to investigate the API",
        isInvestigating: false,
        abortController: null,
      })
    } finally {
      set((s) => s.abortController === ac ? { isInvestigating: false, abortController: null } : {})
    }
  },

  submitUserInput: async (sessionId, userInput) => {
    const prev = get().abortController
    if (prev) prev.abort()

    const ac = new AbortController()
    set({ isProposing: true, proposalError: null, abortController: ac, completedNodes: [] })

    const applySseEvents = (events: unknown[]) => {
      for (const raw of events) {
        if (!isRecord(raw)) continue
        const type = raw.type
        if (type === "progress" && typeof raw.node === "string") {
          set((state) => ({ completedNodes: [...state.completedNodes, raw.node as string] }))
        } else if (type === "final") {
          const utRaw = raw.ui_trigger
          set(() => {
            const uiTrigger: UiTriggerState = isRecord(utRaw)
              ? {
                  component: String(utRaw.component ?? ""),
                  message: typeof utRaw.message === "string" ? utRaw.message : undefined,
                  data: isRecord(utRaw.data) ? utRaw.data : undefined,
                }
              : null
            const base = { abortController: null as AbortController | null, uiTrigger, isProposing: false }
            if (isRecord(utRaw) && utRaw.component === "TemplateApproval" && isRecord(utRaw.data) && typeof utRaw.data.ddl === "string") {
              const columns = TemplateColumnsFromUiTrigger(utRaw.data.columns ?? [])
              const tableName = typeof utRaw.data.tableName === "string" && utRaw.data.tableName.trim() ? utRaw.data.tableName.trim() : "Pending Template"
              return { ...base, templateProposal: { tableName, columns, ddl: utRaw.data.ddl } }
            }
            return base
          })
        }
      }
    }

    try {
      if (IS_MOCK) {
        const connectorId = get().connectorId ?? "meta"
        const selected = isRecord(userInput) && Array.isArray(userInput.columns_selected) ? (userInput.columns_selected as string[]) : []
        let buf = ""
        for await (const sseChunk of mockSubmitInputStream(connectorId, selected)) {
          if (ac.signal.aborted) break
          const { buffer, events } = feedSseBuffer(buf, sseChunk)
          buf = buffer
          applySseEvents(events)
        }
      } else {
        const response = await fetch(`${API_BASE}/api/submit_input`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, user_input: userInput }),
          signal: ac.signal,
        })
        if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`)
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ""
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const { buffer: nextBuf, events } = feedSseBuffer(buffer, decoder.decode(value, { stream: true }))
          buffer = nextBuf
          applySseEvents(events)
        }
      }
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") {
        set({ isProposing: false, abortController: null })
        return
      }
      set({ proposalError: e instanceof Error ? e.message : "Failed to generate Template", isProposing: false, abortController: null })
    } finally {
      set((s) => s.abortController === ac ? { isProposing: false, abortController: null } : {})
    }
  },


  reset: () => {
    const ac = get().abortController
    if (ac) ac.abort()
    set(initialState)
  },
}))