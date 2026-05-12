import type { NextAuthOptions } from "next-auth"
import GoogleProvider from "next-auth/providers/google"
import { refreshGoogleAccessToken } from "./refresh-google-access-token"

const GOOGLE_CLOUD_SCOPE = "https://www.googleapis.com/auth/cloud-platform.read-only"

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID ?? "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "",
      authorization: {
        params: {
          scope: `openid email profile ${GOOGLE_CLOUD_SCOPE}`,
          access_type: "offline",
          prompt: "consent",
          response_type: "code",
        },
      },
    }),
  ],
  pages: {
    signIn: "/login",
  },
  callbacks: {
    async jwt({ token, account, profile }) {
      if (account && profile) {
        token.name = profile.name ?? token.name
        token.email = profile.email ?? token.email
        token.picture = (profile as { picture?: string }).picture ?? token.picture
      }
      if (account) {
        token.accessToken = account.access_token
        token.refreshToken = account.refresh_token ?? token.refreshToken
        token.accessTokenExpires = account.expires_at
          ? account.expires_at * 1000
          : Date.now() + ((account as { expires_in?: number }).expires_in ?? 3600) * 1000
        token.error = undefined
        return token
      }
      if (token.error === "RefreshAccessTokenError") {
        return token
      }
      const expires = token.accessTokenExpires as number | undefined
      if (expires && Date.now() < expires - 60_000) {
        return token
      }
      if (token.refreshToken) {
        return await refreshGoogleAccessToken(token)
      }
      return token
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.name = token.name as string
        session.user.email = token.email as string
        session.user.image = (token.picture as string) ?? session.user.image
      }
      return session
    },
  },
  secret: process.env.NEXTAUTH_SECRET,
}
