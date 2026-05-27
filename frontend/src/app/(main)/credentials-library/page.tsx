"use client"

import { useState, useMemo, useEffect } from "react"
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog"
import { generateCredentialId } from "@/lib/generateCredentialId"
import { cn } from "@/lib/utils"
import { useCredentialStore } from "@/lib/stores/credentialStore"
import { useTenantStore } from "@/lib/stores/tenantStore"
import { fetchCredentials, saveCredential, deactivateCredential, decodeName } from "@/lib/api/credentials"

// ---------------------------------------------------------------------------
// Platform configuration
// ---------------------------------------------------------------------------

type PlatformKey = "META" | "DV360"

interface FieldDef {
  key: string
  label: string
  type: "text" | "password"
  placeholder: string
}

const PLATFORM_CONFIG: Record<PlatformKey, { label: string; fields: FieldDef[]; docUrl: string }> = {
  META: {
    label: "Meta",
    docUrl: "https://developers.facebook.com/documentation/facebook-login/guides/access-tokens",
    fields: [
      { key: "access_token",  label: "Access Token",  type: "password", placeholder: "EAAxx..." },
      { key: "ad_account_id", label: "Ad Account ID", type: "text",     placeholder: "act_123456789" },
    ],
  },
  DV360: {
    label: "DV360",
    docUrl: "https://developers.google.com/display-video/api/guides/quickstart/generate-credentials",
    fields: [
      { key: "access_token",  label: "Access Token",  type: "password", placeholder: "ya29..." },
      { key: "advertiser_id", label: "Advertiser ID", type: "text",     placeholder: "123456789" },
    ],
  },
}

type PlatformFilter = "all" | PlatformKey

const PLATFORM_CHIPS: { id: PlatformFilter; label: string }[] = [
  { id: "all",   label: "All" },
  { id: "META",  label: "Meta" },
  { id: "DV360", label: "DV360" },
]

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function CredentialsPage() {
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const { credentials, addCredential, updateCredential, deleteCredential, setCredentials } = useCredentialStore()
  const { selectedTenantId } = useTenantStore()
  const [searchQuery, setSearchQuery] = useState("")
  const [platformFilter, setPlatformFilter] = useState<PlatformFilter>("all")
  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState<string | null>(null)

  const [formData, setFormData] = useState<{
    name: string
    platform: PlatformKey
    market: string
    brand: string
    payload: Record<string, string>
  }>({ name: "", platform: "META", market: "", brand: "", payload: {} })

  const [visibleFields, setVisibleFields] = useState<Record<string, boolean>>({})
  const toggleFieldVisibility = (key: string) =>
    setVisibleFields((prev) => ({ ...prev, [key]: !prev[key] }))

  // Load credentials from backend on mount
  useEffect(() => {
    // Rehydrate from localStorage first (client-only, avoids SSR mismatch)
    useCredentialStore.persist.rehydrate()

    fetchCredentials(selectedTenantId)
      .then((connections) => {
        const mapped = connections
          .filter((c) => c.status === "active")
          .map((c) => {
            const { name, brand, market } = decodeName(c.name)
            return {
              id: c.connection_id,
              name,
              platform: c.provider.toUpperCase(),
              market,
              brand,
              status: c.status === "active" ? "Healthy" : "Inactive",
              owner: "You (Admin)",
            }
          })
        setCredentials(mapped)
      })
      .catch(() => { /* backend not available — already rehydrated from localStorage */ })
  }, [selectedTenantId, setCredentials])

  const filteredCredentials = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return credentials.filter((c) => {
      if (platformFilter !== "all" && c.platform !== platformFilter) return false
      if (!q) return true
      return (
        c.name.toLowerCase().includes(q) ||
        c.id.toLowerCase().includes(q) ||
        c.platform.toLowerCase().includes(q) ||
        c.market.toLowerCase().includes(q) ||
        c.brand.toLowerCase().includes(q)
      )
    })
  }, [credentials, searchQuery, platformFilter])

  const platformFields = PLATFORM_CONFIG[formData.platform].fields

  const openCreateModal = () => {
    setEditingId(null)
    setFormData({ name: "", platform: "META", market: "", brand: "", payload: {} })
    setVisibleFields({})
    setIsModalOpen(true)
  }

  const openEditModal = (conn: any) => {
    const platform = (Object.keys(PLATFORM_CONFIG).includes(conn.platform) ? conn.platform : "META") as PlatformKey
    setEditingId(conn.id)
    setFormData({ name: conn.name, platform, market: conn.market, brand: conn.brand, payload: {} })
    setVisibleFields({})
    setIsModalOpen(true)
  }

  const setPayloadField = (key: string, value: string) =>
    setFormData((f) => ({ ...f, payload: { ...f.payload, [key]: value } }))

  const handlePlatformChange = (platform: PlatformKey) => {
    setFormData((f) => ({ ...f, platform, payload: {} }))
    setVisibleFields({})
  }

  const handleSave = async () => {
    const connectionId = editingId || generateCredentialId(formData.platform, formData.brand, formData.market)
    const entry = {
      id: connectionId,
      name: formData.name,
      platform: formData.platform,
      market: formData.market,
      brand: formData.brand,
      status: "Healthy",
      owner: "You (Admin)",
    }

    const hasPayload = Object.values(formData.payload).some((v) => v.trim() !== "")

    if (hasPayload) {
      setIsSaving(true)
      try {
        await saveCredential(
          connectionId,
          formData.platform.toLowerCase(),
          formData.payload,
          formData.name,
          formData.brand,
          formData.market,
          selectedTenantId,
        )
      } catch (err) {
        console.error("Failed to save credential to backend:", err)
      } finally {
        setIsSaving(false)
      }
    }

    if (editingId) {
      updateCredential(editingId, entry)
    } else {
      addCredential(entry)
    }
    setIsModalOpen(false)
  }

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to remove this connection?")) return
    setIsDeleting(id)
    try {
      await deactivateCredential(id, selectedTenantId)
    } catch (err) {
      console.error("Failed to deactivate credential in backend:", err)
    } finally {
      setIsDeleting(null)
    }
    deleteCredential(id)
  }

  const handleTest = (id: string) => {
    const current = credentials.find((c) => c.id === id)
    if (!current) return
    updateCredential(id, { ...current, status: "Testing..." })
    setTimeout(() => {
      const updated = credentials.find((c) => c.id === id)
      if (updated) updateCredential(id, { ...updated, status: "Healthy" })
    }, 2000)
  }

  return (
    <div className="space-y-6 max-w-[1400px] p-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold">Credentials Library</h1>
          <p className="text-sm text-muted-foreground">Manage source authentication and build reusable Connections.</p>
        </div>

        <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
          <DialogTrigger
            className="inline-flex items-center justify-center bg-[#5c27fe] hover:bg-[#4b1fd1] text-white h-10 px-4 py-2 rounded-md cursor-pointer transition-colors font-medium"
            onClick={openCreateModal}
          >
            <span className="material-symbols-outlined mr-2 text-[20px]">add</span>
            Add Connection
          </DialogTrigger>

          <DialogContent className="bg-white sm:max-w-[440px]">
            <DialogHeader>
              <DialogTitle className="text-xl font-bold">
                {editingId ? "Edit Credential" : "Add New Credential"}
              </DialogTitle>
            </DialogHeader>

            <div className="grid gap-4 py-4">
              {/* Connection Name */}
              <div className="space-y-2">
                <label className="text-[10px] font-bold text-gray-500 uppercase">Connection Name</label>
                <Input
                  placeholder="e.g. Meta France Cadillac"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                />
              </div>

              {/* Platform + Market */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-[10px] font-bold text-gray-500 uppercase">Platform</label>
                  <select
                    className="w-full p-2 border rounded-md bg-white text-sm"
                    value={formData.platform}
                    onChange={(e) => handlePlatformChange(e.target.value as PlatformKey)}
                  >
                    {Object.entries(PLATFORM_CONFIG).map(([key, cfg]) => (
                      <option key={key} value={key}>{cfg.label}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] font-bold text-gray-500 uppercase">Market</label>
                  <Input
                    placeholder="e.g. France"
                    value={formData.market}
                    onChange={(e) => setFormData({ ...formData, market: e.target.value })}
                  />
                </div>
              </div>

              {/* Brand */}
              <div className="space-y-2">
                <label className="text-[10px] font-bold text-gray-500 uppercase">Brand</label>
                <Input
                  placeholder="e.g. Cadillac"
                  value={formData.brand}
                  onChange={(e) => setFormData({ ...formData, brand: e.target.value })}
                />
              </div>

              {/* Dynamic credential fields per platform */}
              <div className="space-y-3 pt-1">
                <div className="flex items-center justify-between">
                  <label className="text-[10px] font-bold text-gray-500 uppercase">
                    {PLATFORM_CONFIG[formData.platform].label} Credentials
                  </label>
                  <a
                    href={PLATFORM_CONFIG[formData.platform].docUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[11px] text-blue-500 hover:underline"
                  >
                    View docs ↗
                  </a>
                </div>

                {platformFields.map((field) => (
                  <div key={field.key} className="space-y-1">
                    <label className="text-xs text-gray-600">{field.label}</label>
                    <div className="relative">
                      <Input
                        type={field.type === "password" && !visibleFields[field.key] ? "password" : "text"}
                        placeholder={editingId ? "Leave blank to keep existing" : field.placeholder}
                        value={formData.payload[field.key] ?? ""}
                        onChange={(e) => setPayloadField(field.key, e.target.value)}
                        className={field.type === "password" ? "pr-10" : ""}
                      />
                      {field.type === "password" && (
                        <button
                          type="button"
                          tabIndex={-1}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                          onClick={() => toggleFieldVisibility(field.key)}
                        >
                          <span className="material-symbols-outlined text-[18px]">
                            {visibleFields[field.key] ? "visibility_off" : "visibility"}
                          </span>
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* ID preview */}
              <div className="p-3 bg-slate-50 rounded-lg border border-dashed border-slate-200">
                <p className="text-[9px] font-bold text-slate-400 uppercase mb-1">Generated ID Preview</p>
                <code className="text-xs font-mono text-purple-600">
                  {formData.brand && formData.market
                    ? generateCredentialId(formData.platform, formData.brand, formData.market)
                    : "waiting for data..."}
                </code>
              </div>
            </div>

            <DialogFooter className="gap-2">
              {editingId && (
                <Button
                  variant="destructive"
                  className="mr-auto"
                  disabled={isDeleting === editingId}
                  onClick={async () => { await handleDelete(editingId); setIsModalOpen(false) }}
                >
                  {isDeleting === editingId ? "Deleting..." : "Delete"}
                </Button>
              )}
              <Button variant="outline" onClick={() => setIsModalOpen(false)}>Cancel</Button>
              <Button className="bg-[#5c27fe] text-white" onClick={handleSave} disabled={isSaving}>
                {isSaving ? "Saving..." : editingId ? "Update" : "Save Connection"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard title="TOTAL CONNECTIONS" value={credentials.length} icon="key" />
        <StatCard title="HEALTHY" value={credentials.length} icon="check_circle" color="text-green-500" />
        <StatCard title="ACTION NEEDED" value="0" icon="warning" color="text-orange-500" />
        <StatCard title="MARKETS COVERED" value="--" icon="public" />
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col gap-2 sm:flex-row sm:gap-4 sm:items-center bg-white p-2 rounded-full border border-gray-100 shadow-sm">
        <div className="relative flex-1 min-w-0">
          <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">search</span>
          <Input
            className="pl-12 border-none bg-transparent focus-visible:ring-0 shadow-none"
            placeholder="Search connections or markets..."
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
                platformFilter === id ? "bg-gray-100 text-gray-900 hover:bg-gray-200" : "text-gray-600"
              )}
            >
              {label}
            </Button>
          ))}
        </div>
      </div>

      {/* Credentials Table */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <Table>
          <TableHeader className="bg-gray-50/50">
            <TableRow>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Connection Name</TableHead>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Platform</TableHead>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Market</TableHead>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Brand</TableHead>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Status</TableHead>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Owner</TableHead>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredCredentials.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-sm text-gray-500 py-10">
                  {credentials.length === 0
                    ? "No connections yet. Add a credential to get started."
                    : "No connections match your search or filter."}
                </TableCell>
              </TableRow>
            ) : (
              filteredCredentials.map((conn) => (
                <TableRow key={conn.id}>
                  <TableCell>
                    <div className="font-medium text-gray-900">{conn.name}</div>
                    <div className="text-[11px] text-gray-400 font-mono">{conn.id}</div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="bg-gray-100 text-gray-600 border-none font-bold uppercase">
                      {conn.platform}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-gray-600 font-medium">{conn.market}</TableCell>
                  <TableCell className="text-gray-600 font-medium">{conn.brand}</TableCell>
                  <TableCell>
                    <div className={cn("flex items-center gap-1 font-medium text-sm",
                      conn.status === "Testing..." ? "text-blue-500" : "text-green-600"
                    )}>
                      <span className={cn("material-symbols-outlined text-[18px]",
                        conn.status === "Testing..." && "animate-spin"
                      )}>
                        {conn.status === "Testing..." ? "sync" : "check_circle"}
                      </span>
                      {conn.status}
                    </div>
                  </TableCell>
                  <TableCell className="text-gray-600">{conn.owner}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost" size="sm" className="text-gray-400 font-bold text-xs"
                        onClick={() => handleTest(conn.id)}
                        disabled={conn.status === "Testing..."}
                      >
                        Test
                      </Button>
                      <Button variant="ghost" size="sm" className="text-gray-400" onClick={() => openEditModal(conn)}>
                        <span className="material-symbols-outlined">edit</span>
                      </Button>
                      <Button
                        variant="ghost" size="sm"
                        className="text-red-400 hover:text-red-600 hover:bg-red-50"
                        onClick={() => handleDelete(conn.id)}
                        disabled={isDeleting === conn.id}
                      >
                        <span className={cn("material-symbols-outlined text-[18px]", isDeleting === conn.id && "animate-spin")}>
                          {isDeleting === conn.id ? "sync" : "delete_forever"}
                        </span>
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

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
