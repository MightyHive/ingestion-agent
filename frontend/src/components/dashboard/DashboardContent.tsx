"use client"

import Link from "next/link"
import { quickActions } from "@/lib/mock-data"
import ConnectorHealthLog from "@/components/dashboard/ConnectorHealthLog"
import DashboardKpiCards from "@/components/dashboard/DashboardKpiCards"
import OnboardingGuide from "@/components/dashboard/OnboardingGuide"

export default function DashboardContent() {
  return (
    <div className="space-y-6 max-w-[1400px]">
      <div>
        <h1 className="text-2xl font-semibold text-on-surface">Dashboard</h1>
        <p className="text-sm text-on-surface-variant mt-0.5">
          Platform health summary and operational overview
        </p>
      </div>

      <OnboardingGuide />

      <DashboardKpiCards />

      <div className="bg-card rounded-2xl shadow-sm border border-border p-5 flex flex-col gap-4 max-w-md">
        <h2 className="font-semibold text-on-surface flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-lg">bolt</span>
          Quick Actions
        </h2>
        <div className="grid grid-cols-2 gap-2">
          {quickActions.map((qa) => (
            <Link
              key={qa.id}
              href={qa.href}
              className="flex flex-col items-center gap-2 p-3 rounded-xl bg-muted/50 hover:bg-muted transition-colors"
            >
              <span className="material-symbols-outlined text-primary text-xl">{qa.icon}</span>
              <span className="text-xs font-medium text-on-surface text-center">{qa.label}</span>
            </Link>
          ))}
        </div>
      </div>

      <ConnectorHealthLog />
    </div>
  )
}
