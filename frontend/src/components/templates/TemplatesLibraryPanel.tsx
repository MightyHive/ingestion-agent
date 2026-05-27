"use client"

import { useMemo, useState } from "react"
import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from "@/components/ui/table"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Label } from "@/components/ui/label"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import Link from "next/link"
import { useTemplateStore, type SavedTemplate } from "@/lib/stores/templateStore"
import { buildBigQueryCreateDdl } from "@/lib/bigquery-ddl"

const PLATFORM_DISPLAY: Record<string, string> = {
  meta: "Meta",
  tiktok: "TikTok",
  youtube: "YouTube",
  cm360: "CM360",
  dv360: "DV360",
  google_ads: "Google Ads",
}

const PLATFORM_SEED = ["meta", "tiktok", "youtube", "cm360", "dv360", "google_ads"] as const

function templatePlatformLabel(stored: string) {
  return PLATFORM_DISPLAY[stored] ?? stored
}

const selectClass =
  "w-full min-w-0 px-3 py-2 border border-border rounded-lg bg-background text-sm text-on-surface outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"

function StatCard({
  title,
  value,
  icon,
  color = "text-gray-400",
}: {
  title: string
  value: number
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

export default function TemplatesLibraryPanel() {
  const { templates, updateTemplate, deleteTemplate } = useTemplateStore()
  const [searchQuery, setSearchQuery] = useState("")
  const [platformFilter, setPlatformFilter] = useState<string>("all")
  const [endpointFilter, setEndpointFilter] = useState<string>("all")

  const endpointOptions = useMemo(() => {
    const u = Array.from(new Set(templates.map((t) => t.endpoint))).sort()
    return u
  }, [templates])

  const platformFilterOptions = useMemo(() => {
    const s = new Set<string>([...PLATFORM_SEED])
    templates.forEach((t) => s.add(t.platform))
    return Array.from(s).sort()
  }, [templates])

  const filteredTemplates = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return templates.filter((t) => {
      if (platformFilter !== "all" && t.platform !== platformFilter) return false
      if (endpointFilter !== "all" && t.endpoint !== endpointFilter) return false
      if (!q) return true
      return (
        t.tableName.toLowerCase().includes(q) ||
        t.id.toLowerCase().includes(q) ||
        t.platform.toLowerCase().includes(q) ||
        templatePlatformLabel(t.platform).toLowerCase().includes(q) ||
        t.endpoint.toLowerCase().includes(q)
      )
    })
  }, [templates, searchQuery, platformFilter, endpointFilter])

  const [editOpen, setEditOpen] = useState(false)
  const [editing, setEditing] = useState<SavedTemplate | null>(null)
  const [editName, setEditName] = useState("")
  const [editPlatform, setEditPlatform] = useState("")
  const [editEndpoint, setEditEndpoint] = useState("")

  const [previewTemplate, setPreviewTemplate] = useState<SavedTemplate | null>(null)

  const mergedEditEndpoints = useMemo(() => {
    const s = new Set(endpointOptions)
    if (editEndpoint) s.add(editEndpoint)
    return Array.from(s).sort()
  }, [endpointOptions, editEndpoint])

  const mergedEditPlatforms = useMemo(() => {
    const s = new Set<string>([...PLATFORM_SEED])
    templates.forEach((t) => s.add(t.platform))
    if (editPlatform) s.add(editPlatform)
    return Array.from(s).sort()
  }, [templates, editPlatform])

  function openEdit(t: SavedTemplate) {
    setEditing(t)
    setEditName(t.tableName)
    setEditPlatform(t.platform)
    setEditEndpoint(t.endpoint)
    setEditOpen(true)
  }

  function handleSaveEdit() {
    if (!editing) return
    const name = editName.trim()
    const platform = editPlatform.trim()
    const endpoint = editEndpoint.trim()
    if (!name || !platform || !endpoint) return

    const nextDdl = buildBigQueryCreateDdl(name, editing.columns, {
      projectId: "project",
      dataset: "dataset",
    })

    updateTemplate(editing.id, {
      tableName: name,
      platform,
      endpoint,
      ddl: nextDdl,
    })
    setEditOpen(false)
    setEditing(null)
  }

  return (
    <div id="templates" className="space-y-6 max-w-[1400px] scroll-mt-24">
      <div className="flex justify-between items-center flex-wrap gap-4">
        <div>
          <h2 className="text-xl font-bold text-on-surface">Templates library</h2>
          <p className="text-sm text-muted-foreground">
            Manage reusable templates for data extraction.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/export-planner"
            className="inline-flex h-10 items-center justify-center rounded-md border border-border bg-white px-4 text-sm font-medium text-on-surface transition-colors hover:bg-muted"
          >
            <span className="material-symbols-outlined mr-2 text-[20px]">schedule_send</span>
            Export Scheduler
          </Link>
          <Link
            href="/data-connection#templates"
            className="inline-flex h-10 items-center justify-center rounded-md bg-[#5c27fe] px-4 text-sm font-medium text-white transition-colors hover:bg-[#4b1fd1]"
          >
            <span className="material-symbols-outlined mr-2 text-[20px]">add</span>
            Add template
          </Link>
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

      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end bg-white p-4 rounded-xl border border-gray-100 shadow-sm">
        <div className="relative flex-1 min-w-[200px]">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-[20px]">
            search
          </span>
          <Input
            className="pl-10"
            placeholder="Search by name, ID, or platform…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1 min-w-[140px]">
          <Label className="text-xs text-muted-foreground">Platform</Label>
          <select
            className={selectClass}
            value={platformFilter}
            onChange={(e) => setPlatformFilter(e.target.value)}
            aria-label="Filter by platform"
          >
            <option value="all">All platforms</option>
            {platformFilterOptions.map((id) => (
              <option key={id} value={id}>
                {templatePlatformLabel(id)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex flex-col gap-1 min-w-[160px]">
          <Label className="text-xs text-muted-foreground">Format (report level)</Label>
          <select
            className={selectClass}
            value={endpointFilter}
            onChange={(e) => setEndpointFilter(e.target.value)}
            aria-label="Filter by template format"
          >
            <option value="all">All formats</option>
            {endpointOptions.map((ep) => (
              <option key={ep} value={ep}>
                {ep}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <Table>
          <TableHeader className="bg-gray-50/50">
            <TableRow>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Template name</TableHead>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Platform</TableHead>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Report level</TableHead>
              <TableHead className="w-[260px] text-right font-bold text-[11px] text-gray-500 uppercase">
                Actions
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredTemplates.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-sm text-gray-500 py-10">
                  {templates.length === 0
                    ? "No templates yet. Create one from the wizard above."
                    : "No templates match your search or filters."}
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
                  <TableCell className="text-right">
                    <div className="flex flex-wrap justify-end gap-1">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => setPreviewTemplate(conn)}
                      >
                        Preview
                      </Button>
                      <Button type="button" variant="ghost" size="sm" onClick={() => openEdit(conn)}>
                        Edit
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => deleteTemplate(conn.id)}
                      >
                        Delete
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog
        open={editOpen}
        onOpenChange={(open) => {
          if (!open) {
            setEditOpen(false)
            setEditing(null)
          }
        }}
      >
        <DialogContent className="bg-white sm:max-w-md" showCloseButton>
          <DialogHeader>
            <DialogTitle className="text-xl font-bold">Edit template</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tpl-name">Template name</Label>
              <Input
                id="tpl-name"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="font-mono text-sm"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tpl-platform">Platform</Label>
              <select
                id="tpl-platform"
                className={selectClass}
                value={editPlatform}
                onChange={(e) => setEditPlatform(e.target.value)}
              >
                {mergedEditPlatforms.map((id) => (
                  <option key={id} value={id}>
                    {templatePlatformLabel(id)}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="tpl-endpoint">Format (report level)</Label>
              <select
                id="tpl-endpoint"
                className={selectClass}
                value={editEndpoint}
                onChange={(e) => setEditEndpoint(e.target.value)}
              >
                {mergedEditEndpoints.map((ep) => (
                  <option key={ep} value={ep}>
                    {ep}
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">
                Values come from report levels used in your library (and this template&apos;s current level).
              </p>
            </div>
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="outline" onClick={() => (setEditOpen(false), setEditing(null))}>
              Cancel
            </Button>
            <Button
              type="button"
              className="bg-[#5c27fe] hover:bg-[#4b1fd1]"
              onClick={handleSaveEdit}
              disabled={!editName.trim() || !editPlatform.trim() || !editEndpoint.trim()}
            >
              Save changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={previewTemplate !== null}
        onOpenChange={(open) => {
          if (!open) setPreviewTemplate(null)
        }}
      >
        {previewTemplate && (
          <DialogContent
            className="max-h-[90vh] gap-0 overflow-y-auto bg-white sm:max-w-3xl"
            showCloseButton
          >
            <DialogHeader className="pb-4">
              <DialogTitle className="text-xl font-bold">Template preview</DialogTitle>
              <div className="flex flex-col gap-2 pt-1 text-sm text-muted-foreground">
                <div className="flex flex-wrap items-center gap-2">
                  <code className="rounded-md bg-muted px-2 py-0.5 font-mono text-sm text-primary">
                    {previewTemplate.tableName}
                  </code>
                  <Badge variant="secondary" className="font-bold uppercase">
                    {templatePlatformLabel(previewTemplate.platform)}
                  </Badge>
                  <span className="text-on-surface">· {previewTemplate.endpoint}</span>
                </div>
                <p className="text-xs">
                  {previewTemplate.columns.length} fields · BigQuery-style schema
                </p>
              </div>
            </DialogHeader>

            <div className="rounded-2xl border border-border bg-card p-4">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
                Fields
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="w-48 px-2 py-2 text-left text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
                        Field
                      </th>
                      <th className="w-24 px-2 py-2 text-left text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
                        Type
                      </th>
                      <th className="w-24 px-2 py-2 text-left text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
                        Mode
                      </th>
                      <th className="px-2 py-2 text-left text-xs font-semibold uppercase tracking-wider text-on-surface-variant">
                        Description
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {previewTemplate.columns.map((col) => (
                      <tr key={col.original} className="border-b border-border/50 hover:bg-muted/30">
                        <td className="px-2 py-2">
                          <code className="text-xs font-mono text-on-surface-variant">{col.name}</code>
                        </td>
                        <td className="px-2 py-2">
                          <code className="text-xs font-mono text-on-surface-variant">{col.type}</code>
                        </td>
                        <td className="px-2 py-2">
                          <code className="text-xs font-mono text-on-surface-variant">{col.mode}</code>
                        </td>
                        <td className="px-2 py-2">
                          <span className="text-xs text-on-surface-variant">
                            {col.description?.trim() ? col.description.trim() : "—"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <details className="group mt-4 rounded-2xl border border-border bg-muted/30 open:pb-1">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-on-surface [&::-webkit-details-marker]:hidden">
                <span>DDL preview</span>
                <span className="material-symbols-outlined text-on-surface-variant transition-transform group-open:rotate-180">
                  expand_more
                </span>
              </summary>
              <div className="border-t border-border px-4 pb-4 pt-2">
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap font-mono text-xs leading-relaxed text-on-surface-variant">
                  {previewTemplate.ddl?.trim()
                    ? previewTemplate.ddl
                    : buildBigQueryCreateDdl(previewTemplate.tableName, previewTemplate.columns, {
                        projectId: "project",
                        dataset: "dataset",
                      })}
                </pre>
              </div>
            </details>

            <DialogFooter className="mt-4 border-t pt-4 sm:justify-end">
              <Button type="button" variant="outline" onClick={() => setPreviewTemplate(null)}>
                Close
              </Button>
            </DialogFooter>
          </DialogContent>
        )}
      </Dialog>
    </div>
  )
}
