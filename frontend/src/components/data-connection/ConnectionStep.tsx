"use client"

import { useRouter } from "next/navigation"
import { useState, useEffect } from "react"
import { useConnectorStore } from "@/lib/stores/connectorStore"
import { getConnectorSessionId, getSessionId } from "@/lib/sessions"
import { cn } from "@/lib/utils"

const IS_MOCK = process.env.NEXT_PUBLIC_MOCK === "true"


const MOCK_CONNECTORS = [
  { id: "meta", name: "Meta Ads", description: "Facebook & Instagram campaigns, ad sets, creatives and performance metrics.", category: "Paid Media", apiVersion: "v18.0", color: "#1877F2", initial: "M" },
  { id: "tiktok", name: "TikTok Ads", description: "TikTok For Business campaigns, ad groups, targeting parameters and KPIs.", category: "Paid Media", apiVersion: "v1.3", color: "#010101", initial: "T" },
  { id: "youtube", name: "YouTube Ads", description: "Channel performance, video-level metrics, audience demographics and revenue.", category: "Paid Media", apiVersion: "v2", color: "#FF0000", initial: "Y" },
]

const CONNECTOR_STYLES: Record<string, { color: string; initial: string }> = {
  meta_facebook_ad_insights: { color: "#1877F2", initial: "F" },
  meta:                    { color: "#1877F2", initial: "M" },
  google_ads:              { color: "#4285F4", initial: "G" },
  dv360:                   { color: "#34A853", initial: "D" },
}

const DEFAULT_STYLE = { color: "#6366f1", initial: "?" }


// Recibimos data y onUpdate como props
export default function ConnectionStep({ data, onUpdate }: any) {
  const router = useRouter()
  const store = useConnectorStore()
  useEffect(() =>{
    store.loadCatalog()
  }, [])

  const CONNECTORS = IS_MOCK ? MOCK_CONNECTORS : store.catalogConnectors
  

  // 1. Cambiamos esto para que si el usuario vuelve atrás, 
  // el componente recuerde qué plataforma eligió antes
  const [selected, setSelected] = useState<string | null>(data?.platform || null)


  // Función que maneja el click
  const handleSelect = (id: string, name: string) => {
    setSelected(id); // Actualiza la UI local (el bordecito azul)
    onUpdate({ platform: id});

    void store.selectConnector(id, name)

  };

  return (
    <div className="space-y-6 max-w-[1200px]">
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">Connectors</h1>
        <p className="text-sm text-on-surface-variant mt-0.5">
          Choose your platform. The agents will investigate the API and return the full field catalog available.
        </p>
      </div>
      
    {store.isLoadingCatalog && (
      <p className="text-sm text-on-surface-variant">Cargando conectores...</p>
    )}
    {store.catalogError && (
      <p className="text-sm text-red-600">{store.catalogError}</p>
    )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {CONNECTORS.map((connector) => {
          const style = CONNECTOR_STYLES[connector.id] ?? DEFAULT_STYLE
          return(
          <button 
            key={connector.id} 
            // 2. Usamos nuestra nueva función handleSelect
            onClick={() => handleSelect(connector.id, connector.name)}
            className={`bg-card rounded-2xl border p-5 flex flex-col gap-4 shadow-sm text-left transition-all ${
              selected === connector.id 
                ? "border-primary/50 ring-2 ring-primary/20 bg-primary/5" 
                : "border-border hover:border-primary/30"
            }`}
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div 
                  className="w-10 h-10 rounded-xl flex items-center justify-center text-white font-bold text-base flex-shrink-0" 
                  style={{ backgroundColor: style.color }}
                >
                  {style.initial}
                </div>
                <div>
                  <p className="text-sm font-semibold text-on-surface">{connector.name}</p>
                  <p className="text-xs text-on-surface-variant">Official API</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
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
          </button>)}
        )}
      </div>

      <div className="border-t border-border pt-4">
        <p className="text-xs font-semibold text-on-surface-variant uppercase tracking-wider mb-3">Coming soon</p>
        <div className="flex gap-2 flex-wrap">
          {["Google Ads", "LinkedIn Ads", "DV360", "Custom API"].map((name) => (
            <span key={name} className="text-xs px-3 py-1.5 rounded-lg border border-dashed border-border text-on-surface-variant">
              {name}
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}