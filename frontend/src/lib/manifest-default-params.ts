import type { Manifest, ManifestParam } from "@/lib/stores/connectorStore"

/**
 * Default value for a manifest param when the user does not configure ingestion
 * in Data Connection (window / one_of is applied automatically for API validation).
 */
function paramAutoValue(spec: ManifestParam): unknown | undefined {
  if ("default" in spec && spec.default !== undefined) return spec.default
  const t = (spec.type ?? "string").toLowerCase()
  if (t === "integer" || t === "number") {
    if (typeof spec.minimum === "number") return spec.minimum
    return 1
  }
  if (t === "boolean") return false
  if (t === "string" && Array.isArray(spec.enum) && spec.enum.length > 0) return spec.enum[0]
  return undefined
}

/**
 * Builds `params` merged into `POST /api/run` so `one_of` and required non-field_list
 * constraints pass without showing technical forms in the UI.
 *
 * Picks the first `params.one_of` group where every key can be filled from manifest
 * defaults (or integer minimum fallback).
 */
export function buildDefaultRunParams(manifest: Manifest): Record<string, unknown> {
  const specs = [...manifest.params.required, ...manifest.params.optional]
  const byName = new Map(specs.map((s) => [s.name, s]))
  const groups = manifest.params.one_of ?? []

  if (groups.length === 0) {
    const out: Record<string, unknown> = {}
    for (const s of specs) {
      if (s.type === "field_list") continue
      const v = paramAutoValue(s)
      if (v !== undefined) out[s.name] = v
    }
    return out
  }

  for (const group of groups) {
    const out: Record<string, unknown> = {}
    let ok = true
    for (const name of group) {
      const spec = byName.get(name)
      if (!spec) {
        ok = false
        break
      }
      const v = paramAutoValue(spec)
      if (v === undefined) {
        ok = false
        break
      }
      out[name] = v
    }
    if (ok && Object.keys(out).length === group.length) return out
  }

  return {}
}
