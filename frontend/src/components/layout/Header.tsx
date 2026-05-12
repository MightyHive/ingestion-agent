"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { UserMenu } from "@/components/auth/UserMenu"
import { cn } from "@/lib/utils"

const headerNavClass =
  "text-slate-500 hover:text-slate-700 transition-colors py-1 text-sm font-medium"
const headerNavActive = "text-blue-600 font-semibold border-b-2 border-blue-600 py-1 text-sm"

export default function Header() {
  const pathname = usePathname()

  function navClass(href: string) {
    const active = href === "/" ? pathname === "/" : pathname.startsWith(href)
    return cn(active ? headerNavActive : headerNavClass)
  }

  return (
    <header className="fixed top-0 z-50 flex h-16 w-full items-center justify-between border-b border-slate-100 bg-white px-6">
      <div className="flex items-center gap-8">
        <Link href="/" className="text-xl font-bold tracking-tight text-slate-900">
          Media Data Studio
        </Link>

        <nav className="hidden items-center gap-6 md:flex">
          <Link href="/" className={navClass("/")}>
            Home
          </Link>
        
        </nav>
      </div>

      <div className="flex items-center gap-2">
        <button type="button" className="rounded-lg p-2 transition-colors hover:bg-slate-50">
          <span className="material-symbols-outlined text-slate-500">help</span>
        </button>
        <button type="button" className="rounded-lg p-2 transition-colors hover:bg-slate-50">
          <span className="material-symbols-outlined text-slate-500">notifications</span>
        </button>
        <UserMenu />
      </div>
    </header>
  )
}
