import type { NextAuthOptions } from "next-auth"
import GoogleProvider from "next-auth/providers/google"

export const authOptions: NextAuthOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID ?? "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "",
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
