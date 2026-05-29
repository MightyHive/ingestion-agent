import type { CredentialPlatformId } from "@/lib/platforms/credential-platforms"
import type { PlatformId } from "@/lib/platforms/types"

const CONNECTOR_TO_CREDENTIAL: Record<PlatformId, CredentialPlatformId> = {
  meta: "META",
  tiktok: "TIKTOK",
  youtube: "YOUTUBE",
  google_ads: "GOOGLE_ADS",
  dv360: "DV360",
}

export function connectorIdToCredentialPlatform(connectorId: string | null): CredentialPlatformId | null {
  if (!connectorId) return null
  return CONNECTOR_TO_CREDENTIAL[connectorId as PlatformId] ?? null
}

export function normalizePlatformKey(platform: string): string {
  return platform.trim().toLowerCase().replace(/\s+/g, "_")
}

export function platformsMatch(a: string, b: string): boolean {
  return normalizePlatformKey(a) === normalizePlatformKey(b)
}
