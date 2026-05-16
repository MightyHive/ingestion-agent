"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"

/** Simple Icons CDN slug by `manifest.platform` / catalog `platform` (lowercase). */
const PLATFORM_SLUG: Record<string, string> = {
  meta: "meta",
  tiktok: "tiktok",
  youtube: "youtube",
  google_ads: "googleads",
  dv360: "googledisplayandvideo360",
  google: "google",
}

/** When `platform` is missing (e.g. mock cards), map connector id to slug. */
const ID_SLUG: Record<string, string> = {
  meta: "meta",
  meta_facebook_ad_insights: "meta",
  tiktok: "tiktok",
  youtube: "youtube",
  google_ads: "googleads",
  dv360: "googledisplayandvideo360",
}

function resolveSlug(platform: string | undefined, id: string): string | null {
  const p = platform?.trim().toLowerCase()
  if (p && PLATFORM_SLUG[p]) return PLATFORM_SLUG[p]
  return ID_SLUG[id] ?? null
}

function hexForUrl(color: string): string {
  return color.replace(/^#/, "")
}

type ConnectorAvatarProps = {
  id: string
  /** Catalog / manifest `platform` (e.g. `meta`). */
  platform?: string
  fallbackColor: string
  fallbackInitial: string
  className?: string
}

/**
 * Brand icon via Simple Icons CDN; falls back to colored initial on load error or unknown slug.
 */
export default function ConnectorAvatar({
  id,
  platform,
  fallbackColor,
  fallbackInitial,
  className,
}: ConnectorAvatarProps) {
  const [imgFailed, setImgFailed] = useState(false)
  const slug = resolveSlug(platform, id)

  if (slug && !imgFailed) {
    return (
      <div
        className={cn(
          "flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-border/60 bg-white p-1.5",
          className
        )}
      >
        <img
          src={`https://cdn.simpleicons.org/${slug}/${hexForUrl(fallbackColor)}`}
          alt=""
          width={32}
          height={32}
          className="h-7 w-7 object-contain"
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setImgFailed(true)}
        />
      </div>
    )
  }

  return (
    <div
      className={cn(
        "flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-sm font-bold text-white",
        className
      )}
      style={{ backgroundColor: fallbackColor }}
    >
      {fallbackInitial}
    </div>
  )
}
