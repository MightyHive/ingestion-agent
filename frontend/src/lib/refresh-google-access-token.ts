import type { JWT } from "next-auth/jwt"

type GoogleTokenResponse = {
  access_token?: string
  expires_in?: number
  refresh_token?: string
}

export async function refreshGoogleAccessToken(token: JWT): Promise<JWT> {
  const clientId = process.env.GOOGLE_CLIENT_ID
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET
  const refreshToken = token.refreshToken as string | undefined

  if (!clientId || !clientSecret || !refreshToken) {
    return { ...token, error: "RefreshAccessTokenError" }
  }

  try {
    const res = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        client_id: clientId,
        client_secret: clientSecret,
        grant_type: "refresh_token",
        refresh_token: refreshToken,
      }),
    })

    const refreshed = (await res.json()) as GoogleTokenResponse

    if (!res.ok || !refreshed.access_token) {
      return { ...token, error: "RefreshAccessTokenError" }
    }

    return {
      ...token,
      accessToken: refreshed.access_token,
      accessTokenExpires: Date.now() + (refreshed.expires_in ?? 3600) * 1000,
      refreshToken: refreshed.refresh_token ?? token.refreshToken,
      error: undefined,
    }
  } catch {
    return { ...token, error: "RefreshAccessTokenError" }
  }
}