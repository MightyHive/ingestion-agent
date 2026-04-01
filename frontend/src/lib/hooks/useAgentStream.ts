"use client"

import { useState, useCallback } from "react"
import { mockAgentStream } from "@/lib/mock-agent"

export interface FinalEvent {
  type: "final"
  response_text: string
  requires_human_input: boolean
  ui_trigger?: {
    component: "ColumnSelector" | "AuthForm" | string
    message: string
    data?: { columns?: unknown[] }
  }
}

export type StreamEvent =
  | { type: "connection"; status: string }
  | { type: "progress"; node: string }
  | FinalEvent

const IS_MOCK = process.env.NEXT_PUBLIC_MOCK === "true"
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

async function readStream(
  response: Response,
  onProgress: (node: string) => void,
  onFinal: (event: FinalEvent) => void,
  onConnected: () => void
) {
  const reader = response.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split("\n\n")
    buffer = chunks.pop() ?? ""
    for (const chunk of chunks) {
      const line = chunk.replace(/^data:\s*/, "").trim()
      if (!line) continue
      try {
        const event: StreamEvent = JSON.parse(line)
        if (event.type === "connection") onConnected()
        else if (event.type === "progress") onProgress(event.node)
        else if (event.type === "final") onFinal(event)
      } catch { }
    }
  }
}

async function readMockStream(
  connectorId: string,
  onProgress: (node: string) => void,
  onFinal: (event: FinalEvent) => void,
  onConnected: () => void
) {
  for await (const chunk of mockAgentStream(connectorId)) {
    const line = chunk.replace(/^data:\s*/, "").trim()
    if (!line) continue
    try {
      const event: StreamEvent = JSON.parse(line)
      if (event.type === "connection") onConnected()
      else if (event.type === "progress") onProgress(event.node)
      else if (event.type === "final") onFinal(event)
    } catch { }
  }
}

export function useAgentStream() {
  const [isConnected, setIsConnected] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [completedNodes, setCompletedNodes] = useState<string[]>([])
  const [finalResponse, setFinalResponse] = useState<FinalEvent | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reset = useCallback(() => {
    setIsConnected(false)
    setIsLoading(false)
    setCompletedNodes([])
    setFinalResponse(null)
    setError(null)
  }, [])

  const run = useCallback(async (
    url: string,
    body: Record<string, unknown>,
    connectorId?: string
  ) => {
    setIsLoading(true)
    setError(null)
    setCompletedNodes([])
    setFinalResponse(null)
    const onConnected = () => setIsConnected(true)
    const onProgress = (node: string) => setCompletedNodes(prev => [...prev, node])
    const onFinal = (event: FinalEvent) => { setFinalResponse(event); setIsLoading(false) }
    try {
      if (IS_MOCK) {
        await readMockStream(connectorId ?? "meta", onProgress, onFinal, onConnected)
      } else {
        const response = await fetch(`${API_BASE}${url}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        })
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        if (!response.body) throw new Error("No response body")
        await readStream(response, onProgress, onFinal, onConnected)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido")
      setIsLoading(false)
    }
  }, [])

  const startChat = useCallback(
    (sessionId: string, message: string, connectorId?: string) =>
      run("/api/chat", { session_id: sessionId, message }, connectorId),
    [run]
  )

  const submitInput = useCallback(
    (sessionId: string, userInput: Record<string, unknown> | string) =>
      run("/api/submit_input", { session_id: sessionId, user_input: userInput }),
    [run]
  )

  return { isConnected, isLoading, completedNodes, finalResponse, error, startChat, submitInput, reset }
}