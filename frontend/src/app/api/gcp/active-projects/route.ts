import { NextResponse } from "next/server"
import { getToken } from "next-auth/jwt"
import { cookies } from "next/headers"
import { verifyGcpProjectAccess } from "@/lib/google-cloud-projects"

const ACTIVE_COOKIE = "mds_gcp_active_project"

export async function POST(req: Request) {
  const secret = process.env.NEXTAUTH_SECRET
  if (!secret) {
    return NextResponse.json({ error: "NEXTAUTH_SECRET missing" }, { status: 500 })
  }

  const token = await getToken({ req: req as Parameters<typeof getToken>[0]["req"], secret })
  if (!token?.accessToken || token.error === "RefreshAccessTokenError") {
    return NextResponse.json({ reauthRequired: true }, { status: 401 })
  }

  let body: { projectId?: string }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 })
  }

  const projectId = body.projectId?.trim()
  if (!projectId) {
    return NextResponse.json({ error: "projectId required" }, { status: 400 })
  }

  const allowed = await verifyGcpProjectAccess(token.accessToken as string, projectId)
  if (!allowed) {
    return NextResponse.json({ error: "No access to project" }, { status: 403 })
  }

  const jar = await cookies()
  jar.set(ACTIVE_COOKIE, projectId, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 365,
    secure: process.env.NODE_ENV === "production",
  })

  return NextResponse.json({ ok: true, activeProjectId: projectId })
}