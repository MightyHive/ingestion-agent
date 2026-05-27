"use client"

import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import PlatformLogo from "@/components/platforms/PlatformLogo"
import { generateCredentialId } from "@/lib/generateCredentialId"
import {
  CREDENTIAL_PLATFORMS,
  TOKEN_DOC_URLS,
  type CredentialPlatformId,
} from "@/lib/platforms/credential-platforms"
import { cn } from "@/lib/utils"

export interface CredentialFormData {
  name: string
  platform: CredentialPlatformId
  market: string
  brand: string
  token: string
}

type TestStatus = "idle" | "testing" | "success" | "error"

interface CredentialDrawerProps {
  open: boolean
  editingId: string | null
  formData: CredentialFormData
  onFormChange: (data: CredentialFormData) => void
  onClose: () => void
  onSave: () => void
  onDelete?: (id: string) => void
}

async function validateConnection(formData: CredentialFormData): Promise<{ ok: boolean; message: string }> {
  await new Promise((resolve) => setTimeout(resolve, 1400))

  if (!formData.name.trim() || !formData.market.trim() || !formData.brand.trim()) {
    return { ok: false, message: "Fill in connection name, market, and brand before testing." }
  }

  if (!formData.token.trim() || formData.token.trim().length < 8) {
    return {
      ok: false,
      message: "Token looks invalid or too short. Paste a valid access token from your platform.",
    }
  }

  return {
    ok: true,
    message: `Successfully connected to ${CREDENTIAL_PLATFORMS.find((p) => p.id === formData.platform)?.label ?? formData.platform}.`,
  }
}

export default function CredentialDrawer({
  open,
  editingId,
  formData,
  onFormChange,
  onClose,
  onSave,
  onDelete,
}: CredentialDrawerProps) {
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
  }, [formData.platform, formData.token, formData.market, formData.brand, formData.name])

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
    const result = await validateConnection(formData)
    setTestStatus(result.ok ? "success" : "error")
    setTestMessage(result.message)
  }

  const canSave = testStatus === "success"

  const idPreview =
    formData.brand && formData.market
      ? generateCredentialId(formData.platform, formData.brand, formData.market)
      : null

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
        aria-labelledby="credential-drawer-title"
        className="fixed right-0 top-16 z-50 flex h-[calc(100vh-4rem)] w-full max-w-md flex-col border-l border-border bg-white shadow-2xl"
      >
        <div className="flex items-start gap-4 border-b border-border px-6 py-5">
          <PlatformLogo platform={formData.platform} size="xl" />
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">
              {editingId ? "Edit credential" : "New credential"}
            </p>
            <h2 id="credential-drawer-title" className="mt-1 text-xl font-bold text-on-surface">
              {CREDENTIAL_PLATFORMS.find((p) => p.id === formData.platform)?.label ?? "Platform"}
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {editingId
                ? "Update fields and test again before saving."
                : "Configure authentication for a platform and market."}
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
            <label className="text-[10px] font-bold text-gray-500 uppercase">Connection name</label>
            <Input
              placeholder="e.g. Meta France Cadillac"
              value={formData.name}
              onChange={(e) => onFormChange({ ...formData, name: e.target.value })}
            />
          </div>

          <div className="space-y-2">
            <label className="text-[10px] font-bold text-gray-500 uppercase">Platform</label>
            <div className="grid grid-cols-3 gap-2">
              {CREDENTIAL_PLATFORMS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => onFormChange({ ...formData, platform: p.id })}
                  className={cn(
                    "flex flex-col items-center gap-1.5 rounded-xl border p-2 transition-all",
                    formData.platform === p.id
                      ? "border-primary bg-primary/5 ring-2 ring-primary/20"
                      : "border-border hover:border-primary/30"
                  )}
                >
                  <PlatformLogo platform={p.id} size="sm" />
                  <span className="text-[10px] font-semibold text-on-surface">{p.label}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-[10px] font-bold text-gray-500 uppercase">Market</label>
              <Input
                placeholder="e.g. France"
                value={formData.market}
                onChange={(e) => onFormChange({ ...formData, market: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-bold text-gray-500 uppercase">Brand</label>
              <Input
                placeholder="e.g. Cadillac"
                value={formData.brand}
                onChange={(e) => onFormChange({ ...formData, brand: e.target.value })}
              />
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase">Access token</label>
            <Input
              type="password"
              placeholder="••••••••••••"
              value={formData.token}
              onChange={(e) => onFormChange({ ...formData, token: e.target.value })}
            />
            <a
              href={TOKEN_DOC_URLS[formData.platform]}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-500 hover:underline"
            >
              Need help? View documentation
            </a>
          </div>

          {idPreview && (
            <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-3">
              <p className="text-[9px] font-bold uppercase text-slate-400 mb-1">Generated ID preview</p>
              <code className="text-xs font-mono text-purple-600">{idPreview}</code>
            </div>
          )}

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
              <Button
                type="button"
                variant="destructive"
                onClick={() => onDelete(editingId)}
              >
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
              title={!canSave ? "Test the connection successfully before saving" : undefined}
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
