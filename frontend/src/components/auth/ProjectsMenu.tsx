"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useSession } from "next-auth/react"

type Row = { projectId: string; name: string; lifecycleState: string }

export function ProjectsMenu() {
  const { status } = useSession()
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reauth, setReauth] = useState(false)
  const [rows, setRows] = useState<Row[]>([])
  const [active, setActive] = useState<string | null>(null)
  const [activeName, setActiveName] = useState<string | null>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  const hydratedActive = useRef(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setReauth(false)
    try {
      const res = await fetch("/api/gcp/projects")
      const data = await res.json()
      if (res.status === 401 && data.reauthRequired) {
        setReauth(true)
        setRows([])
        setActive(null)
        setActiveName(null)
        return
      }
      if (!res.ok) throw new Error(data.error ?? res.statusText)
      setRows(data.projects ?? [])
      
      const id = data.activeProjectId ?? null
      setActive(id)
      if (id && Array.isArray(data.projects)) {
        const row = data.projects.find((p: Row) => p.projectId === id)
        setActiveName(row?.name ?? null)
      } else {
        setActiveName(null)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) void load()
  }, [open, load])

  /** Restore active project label from cookie/API without opening the menu. */
  useEffect(() => {
    if (status !== "authenticated") {
      hydratedActive.current = false
      return
    }
    if (hydratedActive.current) return
    hydratedActive.current = true
    void load()
  }, [status, load])

  useEffect(() => {
    if (!open) return
    function onDocClick(ev: MouseEvent) {
      if (!rootRef.current?.contains(ev.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onDocClick)
    return () => document.removeEventListener("mousedown", onDocClick)
  }, [open])

  async function selectProject(projectId: string, displayName: string) {
    setError(null)
    const res = await fetch("/api/gcp/active-projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ projectId }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) {
      setError((data as { error?: string }).error ?? "Could not activate")
      return
    }
    setActive(projectId)
    setActiveName(displayName)
    setOpen(false)
  }

  if (status !== "authenticated") return null

  const buttonLabel = activeName ?? "Projects"

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        title={activeName ?? "GCP projects"}
        className="flex max-w-[14rem] items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        <span className="material-symbols-outlined shrink-0 text-[20px] text-slate-500">cloud</span>
        <span className="min-w-0 truncate">{buttonLabel}</span>
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 max-h-80 overflow-auto rounded-xl border border-slate-200 bg-white p-2 shadow-lg">
          {loading && <p className="p-2 text-sm text-slate-500">Loading…</p>}
          {reauth && (
            <p className="p-2 text-sm text-amber-800">
              Hace falta volver a iniciar sesión para autorizar acceso a Google Cloud.
            </p>
          )}
          {error && <p className="p-2 text-sm text-red-600">{error}</p>}
          {!loading &&
            !reauth &&
            rows.map((p) => (
              <button
                key={p.projectId}
                type="button"
                onClick={() => void selectProject(p.projectId, p.name)}
                className="flex w-full flex-col items-start rounded-lg px-2 py-2 text-left text-sm hover:bg-slate-50"
              >
                <span className="font-medium text-slate-900">{p.name}</span>
                <span className="font-mono text-xs text-slate-500">{p.projectId}</span>
                {active === p.projectId && (
                  <span className="text-xs font-semibold text-emerald-700">Active</span>
                )}
              </button>
            ))}
        </div>
      )}
    </div>
  )
}