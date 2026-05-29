"use client"

import { useMemo, useState } from "react"
import DestinationDrawer, { type DestinationFormData } from "@/components/destinations/DestinationDrawer"
import DestinationLogo from "@/components/platforms/DestinationLogo"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { appendConnectionLog } from "@/lib/stores/connectionHealthLogStore"
import {
  isErrorDestinationStatus,
  isHealthyDestinationStatus,
  useDestinationStore,
} from "@/lib/stores/destinationStore"
import { validateDestinationConnection } from "@/lib/validateConnection"
import { cn } from "@/lib/utils"

const EMPTY_FORM: DestinationFormData = {
  name: "",
  projectId: "",
  region: "",
  serviceAccount: "",
  loadTarget: "BigQuery",
}

export default function DestinationLibraryPage() {
  const { destinations, addDestination, updateDestination, deleteDestination } = useDestinationStore()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [formData, setFormData] = useState<DestinationFormData>(EMPTY_FORM)
  const [searchQuery, setSearchQuery] = useState("")
  const [testingId, setTestingId] = useState<string | null>(null)

  const filteredDestinations = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return destinations
    return destinations.filter(
      (d) =>
        d.name.toLowerCase().includes(q) ||
        d.id.toLowerCase().includes(q) ||
        d.projectId.toLowerCase().includes(q) ||
        d.region.toLowerCase().includes(q) ||
        d.serviceAccount.toLowerCase().includes(q)
    )
  }, [destinations, searchQuery])

  const openCreateDrawer = () => {
    setEditingId(null)
    setFormData(EMPTY_FORM)
    setDrawerOpen(true)
  }

  const openEditDrawer = (dest: (typeof destinations)[0]) => {
    setEditingId(dest.id)
    setFormData({
      name: dest.name,
      projectId: dest.projectId,
      region: dest.region,
      serviceAccount: dest.serviceAccount,
      loadTarget: dest.loadTarget,
    })
    setDrawerOpen(true)
  }

  const closeDrawer = () => setDrawerOpen(false)

  const handleSave = () => {
    const entry = {
      name: formData.name.trim(),
      projectId: formData.projectId.trim(),
      region: formData.region.trim() || "—",
      serviceAccount: formData.serviceAccount.trim() || "—",
      loadTarget: formData.loadTarget,
      connectionStatus: "Healthy" as const,
    }
    if (editingId) {
      updateDestination(editingId, entry)
    } else {
      addDestination(entry)
    }
    setDrawerOpen(false)
  }

  const handleDelete = (id: string) => {
    if (confirm("Are you sure you want to delete this destination?")) {
      deleteDestination(id)
      setDrawerOpen(false)
    }
  }

  const handleRowTest = async (id: string) => {
    const dest = destinations.find((d) => d.id === id)
    if (!dest || testingId) return

    setTestingId(id)
    updateDestination(id, { connectionStatus: "Testing..." })

    const result = await validateDestinationConnection({
      name: dest.name,
      projectId: dest.projectId,
      region: dest.region,
      serviceAccount: dest.serviceAccount,
    })

    appendConnectionLog({
      sourceType: "destination",
      sourceId: id,
      sourceName: dest.name,
      platform: "GCP",
      status: result.ok ? "success" : "failure",
      message: result.message,
    })

    updateDestination(id, {
      connectionStatus: result.ok ? "Healthy" : "Failed",
    })
    setTestingId(null)
  }

  return (
    <div className="space-y-6 max-w-[1400px] p-6">
      <div className="flex justify-between items-center pr-12">
        <div>
          <h1 className="text-2xl font-bold">Data Destinations</h1>
          <p className="text-sm text-muted-foreground">
            GCP projects available as destinations. Connections are saved in the browser.
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

      <DestinationDrawer
        open={drawerOpen}
        editingId={editingId}
        formData={formData}
        onFormChange={setFormData}
        onClose={closeDrawer}
        onSave={handleSave}
        onDelete={handleDelete}
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard title="TOTAL DESTINATIONS" value={destinations.length} icon="home_storage" />
        <StatCard
          title="HEALTHY CONNECTIONS"
          value={destinations.filter((d) => isHealthyDestinationStatus(d.connectionStatus)).length}
          icon="check_circle"
          color="text-green-500"
        />
        <StatCard
          title="DESTINATIONS WITH ERRORS"
          value={destinations.filter((d) => isErrorDestinationStatus(d.connectionStatus)).length}
          icon="error"
          color="text-red-500"
        />
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:gap-4 sm:items-center bg-white p-2 rounded-full border border-gray-100 shadow-sm">
        <div className="relative flex-1 min-w-0">
          <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">
            search
          </span>
          <Input
            className="pl-12 border-none bg-transparent focus-visible:ring-0 shadow-none"
            placeholder="Search destinations or project IDs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm overflow-hidden">
        <Table>
          <TableHeader className="bg-gray-50/50">
            <TableRow>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Destination</TableHead>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Project ID</TableHead>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Region</TableHead>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Load target</TableHead>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase">Status</TableHead>
              <TableHead className="font-bold text-[11px] text-gray-500 uppercase text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredDestinations.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-sm text-gray-500 py-10">
                  {destinations.length === 0
                    ? "No destinations yet. Add a GCP project to get started."
                    : "No destinations match your search."}
                </TableCell>
              </TableRow>
            ) : (
              filteredDestinations.map((dest) => (
                <TableRow key={dest.id}>
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <DestinationLogo size="md" />
                      <div>
                        <div className="font-medium text-gray-900">{dest.name}</div>
                        <div className="text-[11px] text-gray-400 font-mono">{dest.id}</div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm font-mono text-gray-700">{dest.projectId}</TableCell>
                  <TableCell className="text-gray-600 font-mono text-sm">{dest.region}</TableCell>
                  <TableCell className="text-gray-600 font-medium text-sm">{dest.loadTarget}</TableCell>
                  <TableCell>
                    <div
                      className={cn(
                        "flex items-center gap-1 font-medium text-sm",
                        dest.connectionStatus === "Testing..." && "text-blue-500",
                        dest.connectionStatus === "Healthy" && "text-green-600",
                        isErrorDestinationStatus(dest.connectionStatus) && "text-red-600"
                      )}
                    >
                      <span
                        className={cn(
                          "material-symbols-outlined text-[18px]",
                          dest.connectionStatus === "Testing..." && "animate-spin"
                        )}
                      >
                        {dest.connectionStatus === "Testing..."
                          ? "sync"
                          : dest.connectionStatus === "Healthy"
                            ? "check_circle"
                            : "error"}
                      </span>
                      {dest.connectionStatus}
                    </div>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-gray-400"
                        onClick={() => openEditDrawer(dest)}
                      >
                        <span className="material-symbols-outlined">edit</span>
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-gray-400 font-bold text-xs"
                        onClick={() => handleRowTest(dest.id)}
                        disabled={dest.connectionStatus === "Testing..." || testingId === dest.id}
                      >
                        Test
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-gray-400"
                        onClick={() => {
                          if (confirm("Delete this destination?")) deleteDestination(dest.id)
                        }}
                      >
                        <span className="material-symbols-outlined">delete</span>
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
