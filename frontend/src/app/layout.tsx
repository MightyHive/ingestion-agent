import type { Metadata } from "next"
import { Inter } from "next/font/google"
import { getServerSession } from "next-auth/next"
import "./globals.css"
import { AuthProvider } from "@/components/providers/AuthProvider"
import { authOptions } from "@/lib/auth"

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
})

export const metadata: Metadata = {
  title: "Media Data Studio",
  description: "Enterprise orchestration layer for media extraction and AI readiness.",
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  const session = await getServerSession(authOptions)

  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-full font-sans">
        <AuthProvider session={session}>{children}</AuthProvider>
      </body>
    </html>
  )
}
