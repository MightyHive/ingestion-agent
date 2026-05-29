import {
  CREDENTIAL_PLATFORMS,
  type CredentialPlatformId,
} from "@/lib/platforms/credential-platforms"

export interface CredentialValidationInput {
  name: string
  platform: CredentialPlatformId
  market: string
  brand: string
  token: string
}

export interface DestinationValidationInput {
  name: string
  projectId: string
  region: string
  serviceAccount: string
}

export type ValidationResult = { ok: boolean; message: string }

const MOCK_DELAY_MS = 1400

export async function validateCredentialConnection(
  formData: CredentialValidationInput
): Promise<ValidationResult> {
  await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY_MS))

  if (!formData.name.trim() || !formData.market.trim() || !formData.brand.trim()) {
    return { ok: false, message: "Fill in connection name, market, and brand before testing." }
  }

  if (!formData.token.trim() || formData.token.trim().length < 8) {
    return {
      ok: false,
      message: "Token looks invalid or too short. Paste a valid access token from your platform.",
    }
  }

  const label =
    CREDENTIAL_PLATFORMS.find((p) => p.id === formData.platform)?.label ?? formData.platform

  return {
    ok: true,
    message: `Successfully connected to ${label}.`,
  }
}

export async function validateCredentialFromStore(
  cred: { name: string; platform: string; market: string; brand: string; token?: string }
): Promise<ValidationResult> {
  return validateCredentialConnection({
    name: cred.name,
    platform: cred.platform as CredentialPlatformId,
    market: cred.market,
    brand: cred.brand,
    token: cred.token || "mock-token-for-test",
  })
}

export async function validateDestinationConnection(
  formData: DestinationValidationInput
): Promise<ValidationResult> {
  await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY_MS))

  if (!formData.name.trim() || !formData.projectId.trim()) {
    return { ok: false, message: "Fill in project name and project ID before testing." }
  }

  const sa = formData.serviceAccount.trim()
  if (sa && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(sa)) {
    return { ok: false, message: "Service account email format looks invalid." }
  }

  return {
    ok: true,
    message: `Successfully connected to GCP project ${formData.projectId.trim()}.`,
  }
}
