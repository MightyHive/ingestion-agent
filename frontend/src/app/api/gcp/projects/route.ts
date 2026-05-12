import { NextResponse } from "next/server"
import { getToken } from "next-auth/jwt"
import { cookies } from "next/headers"
import { listGcpProjects } from "@/lib/google-cloud-projects"

const ACTIVE_COOKIE = "mds_gcp_active_project"

export async function GET(req: Request) {
  const secret = process.env.NEXTAUTH_SECRET
  if (!secret) {
    return NextResponse.json({ error: "NEXTAUTH_SECRET missing" }, { status: 500 })
  }

  const token = await getToken({ req: req as Parameters<typeof getToken>[0]["req"], secret })

  if (!token?.accessToken || token.error === "RefreshAccessTokenError") {
    return NextResponse.json({ reauthRequired: true, projects: [] }, { status: 401 })
  }

  try {
    const projects = await listGcpProjects(token.accessToken as string)
    const jar = await cookies()
    const activeProjectId = jar.get(ACTIVE_COOKIE)?.value ?? null
    return NextResponse.json({ projects, activeProjectId })
  } catch (e) {
    const message = e instanceof Error ? e.message : "Unknown error"
    return NextResponse.json({ error: message }, { status: 502 })
  }
}