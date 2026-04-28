"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

const navItems = [
  { href: "/",           icon: "dashboard",      label: "Dashboard" },
  { href: "/credentials-library", icon: "key", label: "Credentials Library"},
  { href: "/templates-library", icon: "grid_layout_side", label: "Templates Library"},
  { href: "/destination-library", icon: "home_storage", label: "Destination Library"},
  { href: "/data-connection", icon: "ads_click",             label: "Data Connection" },
  { href: "/data-export",  icon: "system_update_alt",       label: "Data Export" },
  { href: "/export-planner",     icon: "schedule_send",          label: "Export Planner" },
]

export default function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="fixed left-0 top-16 w-64 h-[calc(100vh-64px)] flex flex-col bg-slate-50 p-4 z-40">

      {/* Zona identidad */}
      <div className="px-2 py-4 mb-2">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center text-white">
            <span className="material-symbols-outlined text-lg">smart_toy</span>
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-on-surface">Autonomous Engine</p>
            <p className="text-[10px] text-on-surface-variant">Powered by Agents</p>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex flex-col gap-1 flex-1">
        {navItems.map((item) => {
          const isActive = item.href === "/"
            ? pathname === "/"
            : pathname.startsWith(item.href)
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-transform ${
                isActive
                  ? "bg-white text-blue-600 shadow-sm"
                  : "text-slate-500 hover:bg-slate-100 hover:translate-x-1"
              }`}
            >
              <span className="material-symbols-outlined">{item.icon}</span>
              <span className="text-sm font-medium">{item.label}</span>
            </Link>
          )
        })}
      </nav>

      {/* Botón */}
      <button className="mt-auto w-full py-3 px-4 bg-gradient-to-br from-primary to-primary-container text-white rounded-xl font-semibold text-sm flex items-center justify-center gap-2">
        <span className="material-symbols-outlined text-sm">add</span>
        New Pipeline
      </button>
    </aside>
  )
}