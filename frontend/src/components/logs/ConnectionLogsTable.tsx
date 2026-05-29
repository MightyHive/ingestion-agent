"use client"

import { useMemo } from "react"
import PlatformLogo from "@/components/platforms/PlatformLogo"
import DestinationLogo from "@/components/platforms/DestinationLogo"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { fmtDateTime } from "@/lib/dashboard-utils"
import { getCredentialPlatformLabel } from "@/lib/platforms/credential-platforms"
import {
  useConnectionHealthLogStore,
  type ConnectionHealthLogEntry,
  type LogStatus,
} from "@/lib/stores/connectionHealthLogStore"
import { cn } from "@/lib/utils"

export interface LogFilters {
  dateFrom: string
  dateTo: string
  platform: string
  status: "all" | LogStatus
}

function statusBadge(status: LogStatus) {
  const isSuccess = status === "success"
  return (
    <span
      className={cn(
        "text-xs font-semibold px-2 py-0.5 rounded-full",
        isSuccess ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"
      )}
    >
      {isSuccess ? "Success" : "Failure"}
    </span>
  )
}

function platformLabel(platform: string, sourceType: ConnectionHealthLogEntry["sourceType"]) {
  if (sourceType === "destination") return "GCP"
  return getCredentialPlatformLabel(platform)
}

export function filterLogs(logs: ConnectionHealthLogEntry[], filters: LogFilters) {
  return logs.filter((entry) => {
    if (filters.status !== "all" && entry.status !== filters.status) return false
    if (filters.platform !== "all" && entry.platform !== filters.platform) return false

    if (filters.dateFrom) {
      const from = new Date(filters.dateFrom)
      from.setHours(0, 0, 0, 0)
      if (new Date(entry.checkedAt) < from) return false
    }
    if (filters.dateTo) {
      const to = new Date(filters.dateTo)
      to.setHours(23, 59, 59, 999)
      if (new Date(entry.checkedAt) > to) return false
    }

    return true
  })
}

interface ConnectionLogsTableProps {
  filters: LogFilters
  limit?: number
}

export default function ConnectionLogsTable({ filters, limit }: ConnectionLogsTableProps) {
  const logs = useConnectionHealthLogStore((s) => s.logs)

  const filtered = useMemo(() => {
    const sorted = [...filterLogs(logs, filters)].sort(
      (a, b) => new Date(b.checkedAt).getTime() - new Date(a.checkedAt).getTime()
    )
    return limit ? sorted.slice(0, limit) : sorted
  }, [logs, filters, limit])

  return (
    <div className="rounded-xl border border-border overflow-hidden bg-white">
      <Table>
        <TableHeader className="bg-gray-50/50">
          <TableRow>
            <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Date / Time</TableHead>
            <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Source</TableHead>
            <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Platform</TableHead>
            <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Status</TableHead>
            <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Error Message</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filtered.length === 0 ? (
            <TableRow>
              <TableCell colSpan={5} className="text-center text-sm text-gray-500 py-10">
                No logs match your filters.
              </TableCell>
            </TableRow>
          ) : (
            filtered.map((entry) => (
              <TableRow key={entry.id}>
                <TableCell className="text-sm text-gray-600 whitespace-nowrap">
                  {fmtDateTime(entry.checkedAt)}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    {entry.sourceType === "destination" ? (
                      <DestinationLogo size="sm" />
                    ) : (
                      <PlatformLogo platform={entry.platform} size="sm" />
                    )}
                    <span className="font-medium text-gray-900">{entry.sourceName}</span>
                  </div>
                </TableCell>
                <TableCell className="text-sm text-gray-700">
                  {platformLabel(entry.platform, entry.sourceType)}
                </TableCell>
                <TableCell>{statusBadge(entry.status)}</TableCell>
                <TableCell className="text-sm text-gray-600 max-w-md">
                  {entry.status === "failure" ? entry.message : "—"}
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}

export function useLogPlatformOptions() {
  const logs = useConnectionHealthLogStore((s) => s.logs)
  return useMemo(() => {
    const platforms = new Set(logs.map((l) => l.platform))
    return ["all", ...Array.from(platforms).sort()]
  }, [logs])
}
