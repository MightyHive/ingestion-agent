export type CredentialPlatformId =
  | "META"
  | "TIKTOK"
  | "YOUTUBE"
  | "CM360"
  | "DV360"
  | "GOOGLE_ADS"

export interface CredentialPlatformConfig {
  id: CredentialPlatformId
  label: string
  color: string
  initial: string
  logoSrc?: string
}

export const CREDENTIAL_PLATFORMS: CredentialPlatformConfig[] = [
  { id: "META", label: "Meta", color: "#1877F2", initial: "M", logoSrc: "/logo-meta.svg" },
  { id: "TIKTOK", label: "TikTok", color: "#010101", initial: "T", logoSrc: "/logo-tiktok.svg" },
  { id: "YOUTUBE", label: "YouTube", color: "#FF0000", initial: "Y", logoSrc: "/logo-youtube.svg" },
  { id: "CM360", label: "CM360", color: "#4285F4", initial: "C" },
  { id: "DV360", label: "DV360", color: "#34A853", initial: "D" },
  { id: "GOOGLE_ADS", label: "Google Ads", color: "#FBBC04", initial: "G", logoSrc: "/logo-google-ads.svg" },
]

export const TOKEN_DOC_URLS: Record<CredentialPlatformId, string> = {
  META: "https://developers.facebook.com/documentation/facebook-login/guides/access-tokens",
  TIKTOK: "https://developers.tiktok.com/doc/login-kit-manage-user-access-tokens/",
  YOUTUBE: "https://developers.google.com/youtube/registering_an_application",
  CM360: "https://developers.google.com/doubleclick-advertisers/getting_started",
  DV360: "https://developers.google.com/display-video/api/guides/quickstart/generate-credentials",
  GOOGLE_ADS: "https://developers.google.com/google-ads/api/docs/get-started/make-first-call",
}

const CONNECTOR_ID_ALIASES: Record<string, CredentialPlatformId> = {
  meta: "META",
  tiktok: "TIKTOK",
  youtube: "YOUTUBE",
  google_ads: "GOOGLE_ADS",
  dv360: "DV360",
}

export function getCredentialPlatform(id: string): CredentialPlatformConfig {
  const direct = CREDENTIAL_PLATFORMS.find((p) => p.id === id.toUpperCase())
  if (direct) return direct

  const viaConnector = CONNECTOR_ID_ALIASES[id.toLowerCase()]
  if (viaConnector) {
    const match = CREDENTIAL_PLATFORMS.find((p) => p.id === viaConnector)
    if (match) return match
  }

  return CREDENTIAL_PLATFORMS[0]
}

export function getCredentialPlatformLabel(id: string): string {
  return getCredentialPlatform(id).label
}
