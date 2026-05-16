"use client"

import { useState, useEffect } from "react"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import ConnectorAvatar from "@/components/data-connection/ConnectorAvatar"
import {
  CONNECTOR_CARD_STYLES,
  DEFAULT_CONNECTOR_CARD_STYLE,
} from "@/lib/connectors/connector-card-styles"

const IS_MOCK = process.env.NEXT_PUBLIC_MOCK === "true"

const MOCK_CONNECTORS = [
  {
    id: "meta",
    platform: "meta",
    name: "Meta Ads",
    description:
      "Facebook & Instagram campaigns, ad sets, creatives and performance metrics.",
    category: "Paid Media",
    apiVersion: "v18.0",
    color: "#1877F2",
    initial: "M",
  },
  {
    id: "tiktok",
    platform: "tiktok",
    name: "TikTok Ads",
    description: "TikTok For Business campaigns, ad groups, targeting parameters and KPIs.",
    category: "Paid Media",
    apiVersion: "v1.3",
    color: "#010101",
    initial: "T",
  },
  {
    id: "youtube",
    platform: "youtube",
    name: "YouTube Ads",
    description: "Channel performance, video-level metrics, audience demographics and revenue.",
    category: "Paid Media",
    apiVersion: "v2",
    color: "#FF0000",
    initial: "Y",
  },
]

export default function ConnectionStep({ data, onUpdate }: { data: { platform?: string }; onUpdate: (d: Record<string, unknown>) => void }) {
  const store = useConnectorStore()
  useEffect(() => {
    void useConnectorStore.getState().loadCatalog()
  }, [])

  const CONNECTORS = IS_MOCK ? MOCK_CONNECTORS : store.catalogConnectors

  const [selected, setSelected] = useState<string | null>(data?.platform || null)

  const handleSelect = (id: string, name: string) => {
    setSelected(id)
    onUpdate({ platform: id })
    void store.selectConnector(id, name)
  }

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">Connectors</h1>
        <p className="text-sm text-on-surface-variant mt-0.5">
          Choose your platform. We load the official field list for the connector you pick.
        </p>
      </div>

      {store.isLoadingCatalog && (
        <p className="text-sm text-on-surface-variant">Cargando conectores...</p>
      )}
      {store.catalogError && <p className="text-sm text-red-600">{store.catalogError}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {CONNECTORS.map((connector) => {
          const style =
            CONNECTOR_CARD_STYLES[connector.id] ?? DEFAULT_CONNECTOR_CARD_STYLE
          const platform =
            "platform" in connector && typeof connector.platform === "string"
              ? connector.platform
              : undefined
          return (
            <button
              key={connector.id}
              type="button"
              onClick={() => handleSelect(connector.id, connector.name)}
              className={`bg-card rounded-2xl border p-5 flex flex-col gap-4 shadow-sm text-left transition-all ${
                selected === connector.id
                  ? "border-primary/50 ring-2 ring-primary/20 bg-primary/5"
                  : "border-border hover:border-primary/30"
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <ConnectorAvatar
                    id={connector.id}
                    platform={platform}
                    fallbackColor={style.color}
                    fallbackInitial={style.initial}
                  />
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-on-surface truncate">{connector.name}</p>
                    <p className="text-xs text-on-surface-variant">Official API</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {selected === connector.id && (
                    <span className="material-symbols-outlined text-primary text-base">check_circle</span>
                  )}
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                    Active
                  </span>
                </div>
              </div>
              <p className="text-sm text-on-surface-variant leading-relaxed flex-1">
                {connector.description}
              </p>
            </button>
          )
        })}
      </div>

      <div className="border-t border-border pt-4">
        <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-3">
          Coming soon
        </p>
        <div className="flex gap-2 flex-wrap">
          {["Google Ads", "LinkedIn Ads", "DV360", "Custom API"].map((name) => (
            <span
              key={name}
              className="text-xs px-3 py-1.5 rounded-lg border border-dashed border-border text-on-surface-variant"
            >
              {name}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}
