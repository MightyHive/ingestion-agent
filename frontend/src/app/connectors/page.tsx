"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import { getConnectorSessionId } from "@/lib/sessions"
import { mockAgentStream } from "@/lib/mock-agent"
import type { Column } from "@/components/connectors/ColumnSelector"
import { cn } from "@/lib/utils"

const IS_MOCK = process.env.NEXT_PUBLIC_MOCK === "true"
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

const CONNECTORS = [
  { id: "meta", name: "Meta Ads", description: "Facebook & Instagram campaigns, ad sets, creatives and performance metrics.", category: "Paid Media", apiVersion: "v18.0", color: "#1877F2", initial: "M" },
  { id: "tiktok", name: "TikTok Ads", description: "TikTok For Business campaigns, ad groups, targeting parameters and KPIs.", category: "Paid Media", apiVersion: "v1.3", color: "#010101", initial: "T" },
  { id: "youtube", name: "YouTube Analytics", description: "Channel performance, video-level metrics, audience demographics and revenue.", category: "Analytics", apiVersion: "v2", color: "#FF0000", initial: "Y" },
]

export default function ConnectorsPage() {
  const router = useRouter()
  const store = useConnectorStore()
  const [selected, setSelected] = useState(null)

  async function handleContinue() {
    if (!selected) return
    const connector = CONNECTORS.find(c => c.id === selected)
    const sessionId = getConnectorSessionId(selected)
    store.setConnector(selected, connector.name, sessionId)
    store.setInvestigating(true)
    router.push("/selectors")

    try {
      if (IS_MOCK) {
        for await (const chunk of mockAgentStream(selected)) {
          const line = chunk.replace(/^data:\s*/, "").trim()
          if (!line) continue
          const event = JSON.parse(line)
          if (event.type === "progress") store.addCompletedNode(event.node)
          if (event.type === "final" && event.ui_trigger?.data?.columns) {
            store.setFields(event.ui_trigger.data.columns)
          }
        }
      } else {
        const response = await fetch(`${API_BASE}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, message: `Investigate the ${connector.name} API and return the full field catalog` }),
        })
        if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`)
        const reader = response.body.getReader()
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
              const event = JSON.parse(line)
              if (event.type === "progress") store.addCompletedNode(event.node)
              if (event.type === "final" && event.ui_trigger?.data?.columns) store.setFields(event.ui_trigger.data.columns)
            } catch { }
          }
        }
      }
    } catch (err) {
      store.setInvestigationError(err instanceof Error ? err.message : "Error al investigar la API")
    }
  }

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">Connectors</h1>
        <p className="text-sm text-on-surface-variant mt-0.5">Choose your platform. The agents will investigate the API and return the full field catalog available.</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {CONNECTORS.map((connector) => (
          <button key={connector.id} onClick={() => setSelected(connector.id)}
            className={`bg-card rounded-2xl border p-5 flex flex-col gap-4 shadow-sm text-left transition-all ${selected === connector.id ? "border-primary/50 ring-2 ring-primary/20" : "border-border hover:border-primary/30"}`}>
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl flex items-center justify-center text-white font-bold text-base flex-shrink-0" style={{ backgroundColor: connector.color }}>{connector.initial}</div>
                <div>
                  <p className="text-sm font-semibold text-on-surface">{connector.name}</p>
                  <p className="text-xs text-on-surface-variant">Official API {connector.apiVersion}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {selected === connector.id && <span className="material-symbols-outlined text-primary text-base">check_circle</span>}
                <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">Active</span>
              </div>
            </div>
            <p className="text-sm text-on-surface-variant leading-relaxed flex-1">{connector.description}</p>
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-muted text-on-surface-variant w-fit">{connector.category}</span>
          </button>
        ))}
      </div>
      {selected && (
        <div className="flex justify-end">
          <button onClick={handleContinue} className="flex items-center gap-2 px-6 py-2.5 bg-primary text-white text-sm font-semibold rounded-xl hover:bg-primary/90 transition-colors">
            Keep going with {CONNECTORS.find(c => c.id === selected)?.name}
            <span className="material-symbols-outlined text-base">arrow_forward</span>
          </button>
        </div>
      )}
      <div className="border-t border-border pt-4">
        <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-3">Coming soon</p>
        <div className="flex gap-2 flex-wrap">
          {["Google Ads", "LinkedIn Ads", "DV360", "Custom API"].map((name) => (
            <span key={name} className="text-xs px-3 py-1.5 rounded-lg border border-dashed border-border text-on-surface-variant">{name}</span>
          ))}
        </div>
      </div>
    </div>
  )
}
