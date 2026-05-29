"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import DestinationLogo from "@/components/platforms/DestinationLogo"
import { appendConnectionLog } from "@/lib/stores/connectionHealthLogStore"
import type { DestinationLoadTarget } from "@/lib/stores/destinationStore"
import { validateDestinationConnection } from "@/lib/validateConnection"
import { cn } from "@/lib/utils"

export interface DestinationFormData {
  name: string
  projectId: string
  region: string
  serviceAccount: string
  loadTarget: DestinationLoadTarget
}

type TestStatus = "idle" | "testing" | "success" | "error"

interface DestinationDrawerProps {
  open: boolean
  editingId: string | null
  formData: DestinationFormData
  onFormChange: (data: DestinationFormData) => void
  onClose: () => void
  onSave: () => void
  onDelete?: (id: string) => void
}

export default function DestinationDrawer({
  open,
  editingId,
  formData,
  onFormChange,
  onClose,
  onSave,
  onDelete,
}: DestinationDrawerProps) {
  const [testStatus, setTestStatus] = useState<TestStatus>("idle")
  const [testMessage, setTestMessage] = useState("")

  useEffect(() => {
    if (!open) return
    setTestStatus("idle")
    setTestMessage("")
  }, [open])

  useEffect(() => {
    setTestStatus("idle")
    setTestMessage("")
  }, [formData.name, formData.projectId, formData.region, formData.serviceAccount, formData.loadTarget])

  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [open, onClose])

  const handleTest = async () => {
    setTestStatus("testing")
    setTestMessage("")
    const result = await validateDestinationConnection(formData)
    setTestStatus(result.ok ? "success" : "error")
    setTestMessage(result.message)

    appendConnectionLog({
      sourceType: "destination",
      sourceId: editingId || formData.projectId.trim() || "pending",
      sourceName: formData.name.trim() || "New destination",
      platform: "GCP",
      status: result.ok ? "success" : "failure",
      message: result.message,
    })
  }

  const canSave = testStatus === "success"

  if (!open) return null

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-40 bg-black/20 supports-backdrop-filter:backdrop-blur-[2px]"
        aria-label="Close panel"
        onClick={onClose}
      />

      <aside
        role="dialog"
        aria-modal
        aria-labelledby="destination-drawer-title"
        className="fixed right-0 top-16 z-50 flex h-[calc(100vh-4rem)] w-full max-w-md flex-col border-l border-border bg-white shadow-2xl"
      >
        <div className="flex items-start gap-4 border-b border-border px-6 py-5">
          <DestinationLogo size="xl" />
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">
              {editingId ? "Edit destination" : "New destination"}
            </p>
            <h2 id="destination-drawer-title" className="mt-1 text-xl font-bold text-on-surface">
              Google Cloud Platform
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {editingId
                ? "Update fields and test again before saving."
                : "Register a GCP project as a data destination."}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100"
            aria-label="Close"
          >
            <span className="material-symbols-outlined text-xl">close</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          <div className="space-y-2">
            <label className="text-[10px] font-bold text-gray-500 uppercase">Project name</label>
            <Input
              placeholder="e.g. MDS Production"
              value={formData.name}
              onChange={(e) => onFormChange({ ...formData, name: e.target.value })}
            />
          </div>

          <div className="space-y-2">
            <label className="text-[10px] font-bold text-gray-500 uppercase">Project ID</label>
            <Input
              className="font-mono text-sm"
              placeholder="e.g. mds-prod-421"
              value={formData.projectId}
              onChange={(e) => onFormChange({ ...formData, projectId: e.target.value })}
            />
          </div>

          <div className="space-y-2">
            <label className="text-[10px] font-bold text-gray-500 uppercase">Region</label>
            <Input
              className="font-mono text-sm"
              placeholder="e.g. us-east1"
              value={formData.region}
              onChange={(e) => onFormChange({ ...formData, region: e.target.value })}
            />
          </div>

          <div className="space-y-2">
            <label className="text-[10px] font-bold text-gray-500 uppercase">Service account</label>
            <Input
              className="font-mono text-sm"
              placeholder="name@project.iam.gserviceaccount.com"
              value={formData.serviceAccount}
              onChange={(e) => onFormChange({ ...formData, serviceAccount: e.target.value })}
            />
          </div>

          <div className="space-y-2">
            <label className="text-[10px] font-bold text-gray-500 uppercase">Load target</label>
            <div className="flex gap-2">
              {(["BigQuery", "GCS"] as const).map((target) => (
                <button
                  key={target}
                  type="button"
                  onClick={() => onFormChange({ ...formData, loadTarget: target })}
                  className={cn(
                    "flex-1 rounded-xl border px-3 py-2 text-sm font-semibold transition-all",
                    formData.loadTarget === target
                      ? "border-primary bg-primary/5 ring-2 ring-primary/20"
                      : "border-border hover:border-primary/30"
                  )}
                >
                  {target}
                </button>
              ))}
            </div>
          </div>

          {testMessage && (
            <div
              className={cn(
                "rounded-lg border px-3 py-2 text-sm",
                testStatus === "success" && "border-emerald-200 bg-emerald-50 text-emerald-900",
                testStatus === "error" && "border-red-200 bg-red-50 text-red-900"
              )}
            >
              <div className="flex items-start gap-2">
                <span className="material-symbols-outlined text-[18px] shrink-0">
                  {testStatus === "success" ? "check_circle" : "error"}
                </span>
                {testMessage}
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-border px-6 py-4 space-y-3">
          <Button
            type="button"
            variant="outline"
            className="w-full"
            onClick={handleTest}
            disabled={testStatus === "testing"}
          >
            <span
              className={cn(
                "material-symbols-outlined mr-2 text-[18px]",
                testStatus === "testing" && "animate-spin"
              )}
            >
              {testStatus === "testing" ? "sync" : "link"}
            </span>
            {testStatus === "testing" ? "Testing connection…" : "Test connection"}
          </Button>

          <div className="flex gap-2">
            {editingId && onDelete && (
              <Button type="button" variant="destructive" onClick={() => onDelete(editingId)}>
                Delete
              </Button>
            )}
            <Button type="button" variant="outline" className="flex-1" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="button"
              className="flex-1 bg-[#5c27fe] text-white hover:bg-[#4b1fd1]"
              onClick={onSave}
              disabled={!canSave}
            >
              {editingId ? "Update" : "Save"}
            </Button>
          </div>

          {!canSave && testStatus !== "testing" && (
            <p className="text-center text-xs text-muted-foreground">
              Run Test connection before saving.
            </p>
          )}
        </div>
      </aside>
    </>
  )
}
