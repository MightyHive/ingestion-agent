"use client"

import { useEffect, useState } from "react"
import { usePathname } from "next/navigation"
import { getPageHelp } from "@/lib/page-help-content"
import { cn } from "@/lib/utils"

export default function PageHelp() {
  const pathname = usePathname()
  const [open, setOpen] = useState(false)
  const help = getPageHelp(pathname)

  useEffect(() => {
    setOpen(false)
  }, [pathname])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false)
    }
    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [open])

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed top-[4.5rem] right-6 z-30 flex h-9 w-9 items-center justify-center rounded-full border border-border bg-white text-slate-600 shadow-sm transition-colors hover:bg-slate-50 hover:text-primary"
        aria-label={`Help: ${help.title}`}
        title="Page help"
      >
        <span className="material-symbols-outlined text-[22px]">help</span>
      </button>

      {open && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/20 supports-backdrop-filter:backdrop-blur-[2px]"
          aria-label="Close help panel"
          onClick={() => setOpen(false)}
        />
      )}

      <aside
        role="dialog"
        aria-modal={open}
        aria-labelledby="page-help-title"
        className={cn(
          "fixed right-0 top-16 z-50 flex h-[calc(100vh-4rem)] w-full max-w-md flex-col border-l border-border bg-white shadow-2xl transition-transform duration-300 ease-out",
          open ? "translate-x-0" : "translate-x-full pointer-events-none"
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-5">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">Page guide</p>
            <h2 id="page-help-title" className="mt-1 text-xl font-bold text-on-surface">
              {help.title}
            </h2>
          </div>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100"
            aria-label="Close help"
          >
            <span className="material-symbols-outlined text-xl">close</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          <section>
            <h3 className="text-sm font-semibold text-on-surface">Purpose</h3>
            <p className="mt-2 text-sm leading-relaxed text-on-surface-variant">{help.purpose}</p>
          </section>

          <section>
            <h3 className="text-sm font-semibold text-on-surface">How to use this page</h3>
            <ol className="mt-3 space-y-3">
              {help.steps.map((step, i) => (
                <li key={step} className="flex gap-3 text-sm leading-relaxed text-on-surface-variant">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                    {i + 1}
                  </span>
                  <span className="pt-0.5">{step}</span>
                </li>
              ))}
            </ol>
          </section>
        </div>

        <div className="border-t border-border px-6 py-4">
          <p className="text-xs text-on-surface-variant">
            New to the platform? Work top-down: credentials → exploration → destinations → monitoring → scheduler.
          </p>
        </div>
      </aside>
    </>
  )
}
