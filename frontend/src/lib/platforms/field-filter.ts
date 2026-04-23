import type { FieldRow, PlatformId } from "@/lib/platforms/types"
import { isMetaFieldAllowedAtLevel, type MetaLevel } from "@/lib/platforms/meta/available-fields"

const META_LEVELS: MetaLevel[] = ["campaign", "adset", "ad"]

function isMetaLevel(s: string): s is MetaLevel {
  return (META_LEVELS as string[]).includes(s)
}

/**
 * Keeps only API-valid fields for the selected reporting `scope` (e.g. Meta campaign vs ad).
 * Non-Meta: future per-platform rules; for now all rows pass if a level is set.
 */
export function filterFieldsByReportingLevel(
  platform: PlatformId,
  fields: readonly FieldRow[],
  scope: string | null
): FieldRow[] {
  if (!scope) return []
  if (platform === "meta" && isMetaLevel(scope)) {
    return fields.filter((f) => isMetaFieldAllowedAtLevel(f.id, scope))
  }
  if (["tiktok", "youtube", "google_ads", "dv360"].includes(platform) && scope) {
    return [...fields]
  }
  return [...fields]
}
