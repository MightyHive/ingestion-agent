"use client"

import Link from "next/link"
import ConnectionLogsTable from "@/components/logs/ConnectionLogsTable"
import type { LogFilters } from "@/components/logs/ConnectionLogsTable"

const DASHBOARD_FILTERS: LogFilters = {
  dateFrom: "",
  dateTo: "",
  platform: "all",
  status: "all",
}

export default function ConnectorHealthLog() {
  return (
    <div className="bg-card rounded-2xl border border-border p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="font-semibold text-on-surface flex items-center gap-2">
            <span className="material-symbols-outlined text-primary text-lg">monitoring</span>
            Connection Health Log
          </h2>
          <p className="text-sm text-on-surface-variant mt-0.5">
            Recent connection checks from credentials and destinations.
          </p>
        </div>
        <Link
          href="/logs"
          className="text-xs font-semibold text-primary hover:underline whitespace-nowrap"
        >
          View all logs →
        </Link>
      </div>

      <ConnectionLogsTable filters={DASHBOARD_FILTERS} limit={10} />
    </div>
  )
}
