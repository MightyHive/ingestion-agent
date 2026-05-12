export type GcpProjectRow = {
  projectId: string
  name: string
  lifecycleState: string
}

/** v3 Project resource (search / get). */
type V3Project = {
  name?: string
  projectId?: string
  displayName?: string
  /** v3 lifecycle enum string, e.g. ACTIVE */
  state?: string
}

type SearchProjectsResponse = {
  projects?: V3Project[]
  nextPageToken?: string
}

/**
 * Lists projects visible to the OAuth user via v3 `projects.search` (GET).
 * @see https://docs.cloud.google.com/resource-manager/reference/rest/v3/projects/search
 */
export async function listGcpProjects(accessToken: string): Promise<GcpProjectRow[]> {
  const out: GcpProjectRow[] = []
  let pageToken: string | undefined

  do {
    const url = new URL("https://cloudresourcemanager.googleapis.com/v3/projects:search")
    url.searchParams.set("pageSize", "500")
    if (pageToken) url.searchParams.set("pageToken", pageToken)

    const res = await fetch(url.toString(), {
      method: "GET",
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: "no-store",
    })

    if (!res.ok) {
      const err = await res.text()
      throw new Error(`projects.search failed: ${res.status} ${err}`)
    }

    const data = (await res.json()) as SearchProjectsResponse

    for (const p of data.projects ?? []) {
      const projectId = p.projectId?.trim()
      if (!projectId) continue

      const display = (p.displayName ?? "").trim()
      const state = (p.state ?? "STATE_UNSPECIFIED").trim()

      out.push({
        projectId,
        name: display || projectId,
        lifecycleState: state,
      })
    }
    pageToken = data.nextPageToken
  } while (pageToken)

  return out
    .filter((p) => p.lifecycleState === "ACTIVE")
    .sort((a, b) => a.name.localeCompare(b.name))
}

export async function verifyGcpProjectAccess(
  accessToken: string,
  projectId: string
): Promise<boolean> {
  const res = await fetch(
    `https://cloudresourcemanager.googleapis.com/v3/projects/${encodeURIComponent(projectId)}`,
    { headers: { Authorization: `Bearer ${accessToken}` }, cache: "no-store" }
  )
  return res.ok
}
