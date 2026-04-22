import type { PlatformId, ReportEndpoint } from "@/lib/platforms/types"
import { isPlatformId } from "@/lib/platforms/types"

const REPORT_ENDPOINTS: Record<PlatformId, readonly ReportEndpoint[]> = {
  meta: [
    { id: "campaign", label: "Campaign" },
    { id: "adset", label: "Ad set" },
    { id: "ad", label: "Ad" },
  ],
  tiktok: [
    { id: "campaign", label: "Campaign" },
    { id: "adgroup", label: "Ad group" },
    { id: "ad", label: "Ad" },
  ],
  youtube: [
    { id: "channel", label: "Channel" },
    { id: "campaign", label: "Campaign" },
    { id: "video", label: "Video" },
  ],
  google_ads: [
    { id: "campaign", label: "Campaign" },
    { id: "adgroup", label: "Ad group" },
    { id: "ad", label: "Ad" },
  ],
  dv360: [
    { id: "insertionorder", label: "Insertion order" },
    { id: "lineitem", label: "Line item" },
    { id: "ad", label: "Ad" },
  ],
} as const

const DEFAULT: readonly ReportEndpoint[] = REPORT_ENDPOINTS.meta

/**
 * Object levels used as tabs in the field list (and as reporting `scope` options).
 * Backend can mirror the same `id` values for each platform.
 */
export function getReportEndpoints(platformId: string): readonly ReportEndpoint[] {
  if (isPlatformId(platformId)) {
    return REPORT_ENDPOINTS[platformId]
  }
  return DEFAULT
}
