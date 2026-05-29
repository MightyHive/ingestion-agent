"use client"

import { useMemo, useState } from "react"
import ConnectionLogsTable, {
  type LogFilters,
  useLogPlatformOptions,
} from "@/components/logs/ConnectionLogsTable"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { useConnectionHealthLogStore } from "@/lib/stores/connectionHealthLogStore"
import { getCredentialPlatformLabel } from "@/lib/platforms/credential-platforms"
import { cn } from "@/lib/utils"

const STATUS_OPTIONS = [
  { id: "all" as const, label: "All" },
  { id: "success" as const, label: "Success" },
  { id: "failure" as const, label: "Failure" },
]

export default function LogsPage() {
  const logs = useConnectionHealthLogStore((s) => s.logs)
  const platformOptions = useLogPlatformOptions()

  const [filters, setFilters] = useState<LogFilters>({
    dateFrom: "",
    dateTo: "",
    platform: "all",
    status: "all",
  })

  const stats = useMemo(() => {
    const success = logs.filter((l) => l.status === "success").length
    const failure = logs.filter((l) => l.status === "failure").length
    return { total: logs.length, success, failure }
  }, [logs])

  return (
    <div className="space-y-6 max-w-[1400px] p-6">
      <div>
        <h1 className="text-2xl font-bold">Logs</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Connection check logs from Platform Credentials and Data Destinations.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard title="TOTAL ENTRIES" value={stats.total} icon="list_alt" />
        <StatCard title="SUCCESSFUL" value={stats.success} icon="check_circle" color="text-green-500" />
        <StatCard title="FAILURES" value={stats.failure} icon="error" color="text-red-500" />
      </div>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 space-y-4">
        <p className="text-xs font-bold text-gray-400 uppercase tracking-wider">Filters</p>
        <div className="flex flex-col gap-4 lg:flex-row lg:flex-wrap lg:items-end">
          <div className="space-y-1.5">
            <label className="text-[10px] font-bold text-gray-500 uppercase">From</label>
            <Input
              type="date"
              value={filters.dateFrom}
              onChange={(e) => setFilters((f) => ({ ...f, dateFrom: e.target.value }))}
              className="w-full sm:w-40"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-[10px] font-bold text-gray-500 uppercase">To</label>
            <Input
              type="date"
              value={filters.dateTo}
              onChange={(e) => setFilters((f) => ({ ...f, dateTo: e.target.value }))}
              className="w-full sm:w-40"
            />
          </div>
          <div className="space-y-1.5 flex-1 min-w-[200px]">
            <label className="text-[10px] font-bold text-gray-500 uppercase">Platform</label>
            <div className="flex flex-wrap gap-2">
              {platformOptions.map((p) => (
                <Button
                  key={p}
                  type="button"
                  variant="ghost"
                  onClick={() => setFilters((f) => ({ ...f, platform: p }))}
                  className={cn(
                    "rounded-full px-3 h-8 text-xs font-medium",
                    filters.platform === p
                      ? "bg-gray-100 text-gray-900"
                      : "text-gray-600"
                  )}
                >
                  {p === "all" ? "All" : p === "GCP" ? "GCP" : getCredentialPlatformLabel(p)}
                </Button>
              ))}
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-[10px] font-bold text-gray-500 uppercase">Status</label>
            <div className="flex flex-wrap gap-2">
              {STATUS_OPTIONS.map(({ id, label }) => (
                <Button
                  key={id}
                  type="button"
                  variant="ghost"
                  onClick={() => setFilters((f) => ({ ...f, status: id }))}
                  className={cn(
                    "rounded-full px-3 h-8 text-xs font-medium",
                    filters.status === id ? "bg-gray-100 text-gray-900" : "text-gray-600"
                  )}
                >
                  {label}
                </Button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <ConnectionLogsTable filters={filters} />
    </div>
  )
}

function StatCard({
  title,
  value,
  icon,
  color = "text-gray-400",
}: {
  title: string
  value: string | number
  icon: string
  color?: string
}) {
  return (
    <div className="bg-white p-6 rounded-2xl border border-gray-100 shadow-sm flex justify-between items-start">
      <div>
        <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1">{title}</p>
        <p className="text-3xl font-bold text-gray-900">{value}</p>
      </div>
      <span className={`material-symbols-outlined ${color} opacity-20 text-[32px]`}>{icon}</span>
    </div>
  )
}
