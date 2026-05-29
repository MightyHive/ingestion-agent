"use client"

import { useState, useMemo } from "react"
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import CredentialDrawer, { type CredentialFormData } from "@/components/credentials/CredentialDrawer"
import PlatformLogo from "@/components/platforms/PlatformLogo"
import { generateCredentialId } from "@/lib/generateCredentialId"
import { isHealthyConnectionStatus } from "@/lib/dashboard-utils"
import { getCredentialPlatformLabel } from "@/lib/platforms/credential-platforms"
import { cn } from "@/lib/utils"
import { appendConnectionLog } from "@/lib/stores/connectionHealthLogStore"
import { useCredentialStore } from "@/lib/stores/credentialStore"
import { validateCredentialFromStore } from "@/lib/validateConnection"

type CredentialPlatformFilter = "all" | "META" | "TIKTOK" | "YOUTUBE" | "CM360" | "DV360" | "GOOGLE_ADS"

const PLATFORM_CHIPS: { id: CredentialPlatformFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "META", label: "Meta" },
  { id: "TIKTOK", label: "TikTok" },
  { id: "YOUTUBE", label: "YouTube" },
  { id: "CM360", label: "CM360" },
  { id: "DV360", label: "DV360" },
  { id: "GOOGLE_ADS", label: "Google Ads" },
]

const EMPTY_FORM: CredentialFormData = {
  name: "",
  platform: "META",
  market: "",
  brand: "",
  token: "",
}

export default function CredentialsPage() {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const { credentials, addCredential, updateCredential, deleteCredential } = useCredentialStore()
  const [searchQuery, setSearchQuery] = useState("")
  const [platformFilter, setPlatformFilter] = useState<CredentialPlatformFilter>("all")
  const [formData, setFormData] = useState<CredentialFormData>(EMPTY_FORM)

  const filteredCredentials = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return credentials.filter((c) => {
      if (platformFilter !== "all" && c.platform !== platformFilter) return false
      if (!q) return true
      return (
        c.name.toLowerCase().includes(q) ||
        c.id.toLowerCase().includes(q) ||
        c.platform.toLowerCase().includes(q) ||
        getCredentialPlatformLabel(c.platform).toLowerCase().includes(q) ||
        c.market.toLowerCase().includes(q) ||
        c.brand.toLowerCase().includes(q)
      )
    })
  }, [credentials, searchQuery, platformFilter])

  const openCreateDrawer = () => {
    setEditingId(null)
    setFormData(EMPTY_FORM)
    setDrawerOpen(true)
  }

  const openEditDrawer = (conn: (typeof credentials)[0]) => {
    setEditingId(conn.id)
    setFormData({
      name: conn.name,
      platform: conn.platform as CredentialFormData["platform"],
      market: conn.market,
      brand: conn.brand,
      token: conn.token || "",
    })
    setDrawerOpen(true)
  }

  const closeDrawer = () => setDrawerOpen(false)

  const handleSave = () => {
    const expiresAt = new Date()
    expiresAt.setDate(expiresAt.getDate() + 30)
    const entry = {
      ...formData,
      id: editingId || generateCredentialId(formData.platform, formData.brand, formData.market),
      status: "Healthy",
      owner: "You (Admin)",
      tokenExpiresAt: expiresAt.toISOString(),
    }
    if (editingId) {
      updateCredential(editingId, entry)
    } else {
      addCredential(entry)
    }
    setDrawerOpen(false)
  }

  const handleDelete = (id: string) => {
    if (confirm("Are you sure you want to delete this connection?")) {
      deleteCredential(id)
      setDrawerOpen(false)
    }
  }

  const handleTest = async (id: string) => {
    const currentCred = credentials.find((c) => c.id === id)
    if (!currentCred || currentCred.status === "Testing...") return

    updateCredential(id, { ...currentCred, status: "Testing..." })

    const result = await validateCredentialFromStore(currentCred)

    appendConnectionLog({
      sourceType: "credential",
      sourceId: id,
      sourceName: currentCred.name,
      platform: currentCred.platform,
      status: result.ok ? "success" : "failure",
      message: result.message,
    })

    updateCredential(id, {
      ...currentCred,
      status: result.ok ? "Healthy" : "Action Needed",
    })
  }

  return (
    <div className="space-y-6 max-w-[1400px] p-6">
      <div className="flex justify-between items-center pr-12">
        <div>
          <h1 className="text-2xl font-bold">Platform Credentials</h1>
          <p className="text-sm text-muted-foreground">
            Manage source authentication and build reusable connections.
          </p>
        </div>

        <Button
          type="button"
          className="bg-[#5c27fe] hover:bg-[#4b1fd1] text-white"
          onClick={openCreateDrawer}
        >
          <span className="material-symbols-outlined mr-2 text-[20px]">add</span>
          Add connection
        </Button>
      </div>

      <CredentialDrawer
        open={drawerOpen}
        editingId={editingId}
        formData={formData}
        onFormChange={setFormData}
        onClose={closeDrawer}
        onSave={handleSave}
        onDelete={handleDelete}
      />

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard title="TOTAL CONNECTIONS" value={credentials.length} icon="key" />
        <StatCard
          title="HEALTHY"
          value={credentials.filter((c) => isHealthyConnectionStatus(c.status)).length}
          icon="check_circle"
          color="text-green-500"
        />
        <StatCard
          title="ACTION NEEDED"
          value={credentials.filter((c) => !isHealthyConnectionStatus(c.status)).length}
          icon="warning"
          color="text-orange-500"
        />
        <StatCard title="MARKETS COVERED" value={new Set(credentials.map((c) => c.market)).size || "--"} icon="public" />
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:gap-4 sm:items-center bg-white p-2 rounded-full border border-gray-100 shadow-sm">
        <div className="relative flex-1 min-w-0">
          <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">
            search
          </span>
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
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Connection</TableHead>
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
                    <div className="flex items-center gap-3">
                      <PlatformLogo platform={conn.platform} size="md" />
                      <div>
                        <div className="font-medium text-gray-900">{conn.name}</div>
                        <div className="text-[11px] text-gray-400 font-mono">{conn.id}</div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm font-medium text-gray-700">
                    {getCredentialPlatformLabel(conn.platform)}
                  </TableCell>
                  <TableCell className="text-gray-600 font-medium">{conn.market}</TableCell>
                  <TableCell className="text-gray-600 font-medium">{conn.brand}</TableCell>
                  <TableCell>
                    <div
                      className={cn(
                        "flex items-center gap-1 font-medium text-sm",
                        conn.status === "Testing..." ? "text-blue-500" : "text-green-600"
                      )}
                    >
                      <span
                        className={cn(
                          "material-symbols-outlined text-[18px]",
                          conn.status === "Testing..." && "animate-spin"
                        )}
                      >
                        {conn.status === "Testing..." ? "sync" : "check_circle"}
                      </span>
                      {conn.status}
                    </div>
                  </TableCell>
                  <TableCell className="text-gray-600">{conn.owner}</TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-gray-400"
                        onClick={() => openEditDrawer(conn)}
                      >
                        <span className="material-symbols-outlined">edit</span>
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-gray-400 font-bold text-xs"
                        onClick={() => handleTest(conn.id)}
                        disabled={conn.status === "Testing..."}
                      >
                        Test
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
