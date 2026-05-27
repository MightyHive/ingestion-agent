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
}

export const CREDENTIAL_PLATFORMS: CredentialPlatformConfig[] = [
  { id: "META", label: "Meta", color: "#1877F2", initial: "M" },
  { id: "TIKTOK", label: "TikTok", color: "#010101", initial: "T" },
  { id: "YOUTUBE", label: "YouTube", color: "#FF0000", initial: "Y" },
  { id: "CM360", label: "CM360", color: "#4285F4", initial: "C" },
  { id: "DV360", label: "DV360", color: "#34A853", initial: "D" },
  { id: "GOOGLE_ADS", label: "Google Ads", color: "#FBBC04", initial: "G" },
]

export const TOKEN_DOC_URLS: Record<CredentialPlatformId, string> = {
  META: "https://developers.facebook.com/documentation/facebook-login/guides/access-tokens",
  TIKTOK: "https://developers.tiktok.com/doc/login-kit-manage-user-access-tokens/",
  YOUTUBE: "https://developers.google.com/youtube/registering_an_application",
  CM360: "https://developers.google.com/doubleclick-advertisers/getting_started",
  DV360: "https://developers.google.com/display-video/api/guides/quickstart/generate-credentials",
  GOOGLE_ADS: "https://developers.google.com/google-ads/api/docs/get-started/make-first-call",
}

export function getCredentialPlatform(id: string): CredentialPlatformConfig {
  return CREDENTIAL_PLATFORMS.find((p) => p.id === id) ?? CREDENTIAL_PLATFORMS[0]
}

export function getCredentialPlatformLabel(id: string): string {
  return getCredentialPlatform(id).label
}
