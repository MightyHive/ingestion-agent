"use client"

import { useState } from "react"
import { signOut, useSession } from "next-auth/react"

export function UserMenu() {
  const { data: session, status } = useSession()
  const [imgFailed, setImgFailed] = useState(false)

  if (status === "loading") {
    return <div className="h-8 w-8 shrink-0 animate-pulse rounded-full bg-slate-200" aria-hidden />
  }

  const img = session?.user?.image
  const label = session?.user?.name ?? session?.user?.email ?? "Account"
  const initial = label.slice(0, 1).toUpperCase()
  const showImage = !!img && !imgFailed

  return (
    <div className="ml-2 flex items-center gap-2">
      {showImage ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={img}
          alt=""
          className="h-8 w-8 shrink-0 rounded-full object-cover"
          onError={() => setImgFailed(true)}
        />
      ) : (
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-violet-600 text-xs font-semibold text-white">
          {initial}
        </div>
      )}
      <button
        type="button"
        onClick={() => signOut({ callbackUrl: "/login" })}
        className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
      >
        Sign out
      </button>
    </div>
  )
}
