import { create } from "zustand"
import type { Column } from "@/components/connectors/ColumnSelector"
import { columnsFromUiTriggerData } from "@/lib/ui-trigger-fields"
import { mockAgentStream, mockSubmitInputStream } from "@/lib/mock-agent"

const IS_MOCK = process.env.NEXT_PUBLIC_MOCK === "true"
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export interface ChatMessage {
  type: string
  content: string
}

/** Rich ui_trigger from FastAPI final SSE event (ColumnSelector, SchemaApproval, …). */
export type UiTriggerState = {
  component: string
  message?: string
  data?: Record<string, unknown>
} | null

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null
}

/** Append decoded text, split on SSE event boundaries; only parse complete `data:` JSON lines. */
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
    } catch {
      // Malformed JSON for this chunk — skip
    }
  }
  return { buffer: rest, events }
}

interface ConnectorStore {
  connectorId: string | null
  connectorName: string | null
  sessionId: string | null
  fields: Column[]
  isInvestigating: boolean
  investigationError: string | null
  completedNodes: string[]
  selectedFields: string[]
  schemaProposal: SchemaProposal | null
  isProposing: boolean
  proposalError: string | null

  messages: ChatMessage[]
  uiTrigger: UiTriggerState
  abortController: AbortController | null

  setConnector: (id: string, name: string, sessionId: string) => void
  setInvestigating: (value: boolean) => void
  addCompletedNode: (node: string) => void
  setFields: (fields: Column[]) => void
  setInvestigationError: (error: string | null) => void
  setSelectedFields: (fields: string[]) => void
  setSchemaProposal: (proposal: SchemaProposal) => void
  setProposing: (value: boolean) => void
  setProposalError: (error: string | null) => void
  startInvestigation: (sessionId: string, message: string) => Promise<void>
  submitUserInput: (sessionId: string, userInput: unknown) => Promise<void>
  abortStream: () => void
  reset: () => void
}

export interface SchemaColumn {
  name: string
  original: string
  type: string
  mode: "NULLABLE" | "REQUIRED"
  description?: string
}

export interface SchemaProposal {
  tableName: string
  columns: SchemaColumn[]
  ddl: string
}

/** Map FastAPI ``schema_preview`` / BQSchemaField rows into store columns. */
function schemaColumnsFromUiTrigger(raw: unknown): SchemaColumn[] {
  if (!Array.isArray(raw)) return []
  return raw.map((item): SchemaColumn => {
    if (!isRecord(item)) {
      return { name: "", original: "", type: "STRING", mode: "NULLABLE" }
    }
    const fieldName =
      typeof item.field_name === "string"
        ? item.field_name
        : typeof item.name === "string"
          ? item.name
          : ""
    return {
      name: fieldName,
      original: typeof item.original === "string" ? item.original : fieldName,
      type: typeof item.type === "string" ? item.type : "STRING",
      mode: item.mode === "REQUIRED" ? "REQUIRED" : "NULLABLE",
      description: typeof item.description === "string" ? item.description : undefined,
    }
  })
}

const initialState = {
  connectorId: null,
  connectorName: null,
  sessionId: null,
  fields: [] as Column[],
  isInvestigating: false,
  investigationError: null,
  completedNodes: [] as string[],
  selectedFields: [] as string[],
  schemaProposal: null,
  isProposing: false,
  proposalError: null,
  messages: [] as ChatMessage[],
  uiTrigger: null as UiTriggerState,
  abortController: null as AbortController | null,
}

export const useConnectorStore = create<ConnectorStore>((set, get) => ({
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
      schemaProposal: null,
      messages: [],
      uiTrigger: null,
      abortController: null,
      isInvestigating: false,
    })
  },

  setInvestigating: (value) => set({ isInvestigating: value }),

  addCompletedNode: (node) =>
    set((state) => ({ completedNodes: [...state.completedNodes, node] })),

  setFields: (fields) => set({ fields, isInvestigating: false }),

  setInvestigationError: (error) => set({ investigationError: error, isInvestigating: false }),

  setSelectedFields: (fields) => set({ selectedFields: fields }),

  setSchemaProposal: (proposal) => set({ schemaProposal: proposal, isProposing: false }),

  setProposing: (value) => set({ isProposing: value }),

  setProposalError: (error) => set({ proposalError: error, isProposing: false }),

  abortStream: () => {
    const ac = get().abortController
    if (ac) ac.abort()
    set({ abortController: null, isInvestigating: false, isProposing: false })
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
          const responseText =
            typeof raw.response_text === "string" ? raw.response_text : ""
          const utRaw = raw.ui_trigger
          set((state) => {
            const uiTrigger: UiTriggerState =
              isRecord(utRaw)
                ? {
                    component: String(utRaw.component ?? ""),
                    message:
                      typeof utRaw.message === "string" ? utRaw.message : undefined,
                    data: isRecord(utRaw.data) ? utRaw.data : undefined,
                  }
                : null
            let fields = state.fields
            if (
              isRecord(utRaw) &&
              utRaw.component === "ColumnSelector" &&
              isRecord(utRaw.data)
            ) {
              const mapped = columnsFromUiTriggerData(utRaw.data)
              if (mapped.length) fields = mapped
            }
            return {
              isInvestigating: false,
              abortController: null,
              uiTrigger,
              fields,
              messages: [
                ...state.messages,
                { type: "assistant", content: responseText },
              ],
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

        if (!response.ok || !response.body) {
          throw new Error(`HTTP ${response.status}`)
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ""
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const { buffer: nextBuf, events } = feedSseBuffer(
            buffer,
            decoder.decode(value, { stream: true })
          )
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
        investigationError:
          e instanceof Error ? e.message : "Error al investigar la API",
        isInvestigating: false,
        abortController: null,
      })
    } finally {
      set((s) => {
        if (s.abortController !== ac) return {}
        return { isInvestigating: false, abortController: null }
      })
    }
  },

  submitUserInput: async (sessionId, userInput) => {
    const prev = get().abortController
    if (prev) prev.abort()

    const ac = new AbortController()
    set({
      isProposing: true,
      proposalError: null,
      abortController: ac,
      completedNodes: [],
    })

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
                  message:
                    typeof utRaw.message === "string" ? utRaw.message : undefined,
                  data: isRecord(utRaw.data) ? utRaw.data : undefined,
                }
              : null

            const base = {
              abortController: null as AbortController | null,
              uiTrigger,
              isProposing: false,
            }

            if (
              isRecord(utRaw) &&
              utRaw.component === "SchemaApproval" &&
              isRecord(utRaw.data) &&
              typeof utRaw.data.ddl === "string"
            ) {
              return {
                ...base,
                schemaProposal: {
                  tableName: "Pending Schema",
                  columns: schemaColumnsFromUiTrigger(utRaw.data.columns ?? []),
                  ddl: utRaw.data.ddl,
                },
              }
            }

            return base
          })
        }
      }
    }

    try {
      if (IS_MOCK) {
        const connectorId = get().connectorId ?? "meta"
        const selected =
          isRecord(userInput) && Array.isArray(userInput.columns_selected)
            ? (userInput.columns_selected as string[])
            : []
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

        if (!response.ok || !response.body) {
          throw new Error(`HTTP ${response.status}`)
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ""
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          const { buffer: nextBuf, events } = feedSseBuffer(
            buffer,
            decoder.decode(value, { stream: true })
          )
          buffer = nextBuf
          applySseEvents(events)
        }
      }
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") {
        set({ isProposing: false, abortController: null })
        return
      }
      set({
        proposalError:
          e instanceof Error ? e.message : "Error al generar el schema",
        isProposing: false,
        abortController: null,
      })
    } finally {
      set((s) => {
        if (s.abortController !== ac) return {}
        return { isProposing: false, abortController: null }
      })
    }
  },

  reset: () => {
    const ac = get().abortController
    if (ac) ac.abort()
    set(initialState)
  },
}))
