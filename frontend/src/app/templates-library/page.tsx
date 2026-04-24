"use client"

import { useMemo, useState } from "react"
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { useTemplateStore } from "@/lib/stores/templateStore"

type TemplatePlatformId = "all" | "meta" | "tiktok" | "youtube" | "cm360" | "dv360" | "google_ads"

const PLATFORM_CHIPS: { id: TemplatePlatformId; label: string }[] = [
  { id: "all", label: "All" },
  { id: "meta", label: "Meta" },
  { id: "tiktok", label: "TikTok" },
  { id: "youtube", label: "YouTube" },
  { id: "cm360", label: "CM360" },
  { id: "dv360", label: "DV360" },
  { id: "google_ads", label: "Google Ads" },
]

const PLATFORM_DISPLAY: Record<string, string> = {
  meta: "Meta",
  tiktok: "TikTok",
  youtube: "YouTube",
  cm360: "CM360",
  dv360: "DV360",
  google_ads: "Google Ads",
}

function templatePlatformLabel(stored: string) {
  return PLATFORM_DISPLAY[stored] ?? stored
}

export default function TemplatesLibraryPage() {
  const { templates } = useTemplateStore()
  const [searchQuery, setSearchQuery] = useState("")
  const [platformFilter, setPlatformFilter] = useState<TemplatePlatformId>("all")

  const filteredTemplates = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return templates.filter((t) => {
      if (platformFilter !== "all" && t.platform !== platformFilter) return false
      if (!q) return true
      return (
        t.tableName.toLowerCase().includes(q) ||
        t.id.toLowerCase().includes(q) ||
        t.platform.toLowerCase().includes(q) ||
        templatePlatformLabel(t.platform).toLowerCase().includes(q)
      )
    })
  }, [templates, searchQuery, platformFilter])

  return (
    <div className="space-y-6 max-w-[1400px] p-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold">Templates Library</h1>
          <p className="text-sm text-muted-foreground">Manage reusable templates for data extraction.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard title="TOTAL TEMPLATES" value={templates.length} icon="save" />
        <StatCard
          title="CAMPAIGN TEMPLATES"
          value={templates.filter((t) => t.endpoint === "campaign").length}
          icon="campaign"
        />
        <StatCard title="AD TEMPLATES" value={templates.filter((t) => t.endpoint === "ad").length} icon="ad" />
        <StatCard
          title="ADSET TEMPLATES"
          value={templates.filter((t) => t.endpoint === "adset").length}
          icon="ad_group"
        />
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:gap-4 sm:items-center bg-white p-2 rounded-full border border-gray-100 shadow-sm">
        <div className="relative flex-1 min-w-0">
          <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">
            search
          </span>
          <Input
            className="pl-12 border-none bg-transparent focus-visible:ring-0 shadow-none"
            placeholder="Search by name, ID, or platform..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <div className="flex flex-wrap gap-2 pr-2">
          {PLATFORM_CHIPS.map(({ id, label }) => (
            <Button
              key={id}
              type="button"
              variant="ghost"
              onClick={() => setPlatformFilter(id)}
              className={cn(
                "rounded-full px-4 h-8 text-sm font-medium shrink-0",
                platformFilter === id
                  ? "bg-gray-100 text-gray-900 hover:bg-gray-200"
                  : "text-gray-600"
              )}
            >
              {label}
            </Button>
          ))}
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <Table>
          <TableHeader className="bg-gray-50/50">
            <TableRow>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Template Name</TableHead>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Platform</TableHead>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Report Level</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredTemplates.length === 0 ? (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-sm text-gray-500 py-10">
                  {templates.length === 0
                    ? "No templates yet. Create one from Data Connection."
                    : "No templates match your search or filter."}
                </TableCell>
              </TableRow>
            ) : (
              filteredTemplates.map((conn) => (
                <TableRow key={conn.id}>
                  <TableCell>
                    <div className="font-medium text-gray-900">{conn.tableName}</div>
                    <div className="text-[11px] text-gray-400 font-mono">{conn.id}</div>
                  </TableCell>
                  <TableCell>
                    <Badge
                      variant="secondary"
                      className="bg-gray-100 text-gray-600 border-none font-bold uppercase"
                    >
                      {templatePlatformLabel(conn.platform)}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-gray-600 font-medium">{conn.endpoint}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )

  function StatCard({ title, value, icon, color = "text-gray-400" }: any) {
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
}
