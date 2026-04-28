"use client"

import { useState } from "react"
import DestinationsStep from "@/components/data-export/DestinationsStep"
import { useDestinationStore } from "@/lib/stores/destinationStore"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"

const emptyForm = {
  name: "",
  projectId: "",
  region: "",
  serviceAccount: "",
  status: "BigQuery",
}

export default function DestinationLibraryPage() {
  const addDestination = useDestinationStore((s) => s.addDestination)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [formData, setFormData] = useState(emptyForm)

  const openCreateModal = () => {
    setFormData(emptyForm)
    setIsModalOpen(true)
  }

  const handleSave = () => {
    if (!formData.name.trim() || !formData.projectId.trim()) return
    addDestination({
      name: formData.name.trim(),
      projectId: formData.projectId.trim(),
      region: formData.region.trim() || "—",
      serviceAccount: formData.serviceAccount.trim() || "—",
      status: formData.status.trim() || "BigQuery",
    })
    setIsModalOpen(false)
    setFormData(emptyForm)
  }

  return (
    <div className="space-y-6 max-w-[1400px] p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold">Destination Library</h1>
          <p className="text-sm text-muted-foreground">
            GCP projects available as destinations. Connections are saved in the browser.
          </p>
        </div>
        <Button
          type="button"
          className="shrink-0 bg-[#5c27fe] hover:bg-[#4b1fd1]"
          onClick={openCreateModal}
        >
          <span className="material-symbols-outlined mr-2 text-[20px]">add</span>
          Add connection
        </Button>
      </div>

      <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
        <DialogContent className="bg-white sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle className="text-xl font-bold">Add connection</DialogTitle>
          </DialogHeader>

          <div className="grid gap-4 py-2">
            <div className="space-y-2">
              <label className="text-[10px] font-bold text-gray-500 uppercase">Project name</label>
              <Input
                value={formData.name}
                onChange={(e) => setFormData((f) => ({ ...f, name: e.target.value }))}
                placeholder="e.g. MDS Production"
              />
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-bold text-gray-500 uppercase">Project ID</label>
              <Input
                className="font-mono text-sm"
                value={formData.projectId}
                onChange={(e) => setFormData((f) => ({ ...f, projectId: e.target.value }))}
                placeholder="e.g. mds-prod-421"
              />
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-bold text-gray-500 uppercase">Region</label>
              <Input
                className="font-mono text-sm"
                value={formData.region}
                onChange={(e) => setFormData((f) => ({ ...f, region: e.target.value }))}
                placeholder="e.g. us-east1"
              />
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-bold text-gray-500 uppercase">Service account</label>
              <Input
                className="font-mono text-sm"
                value={formData.serviceAccount}
                onChange={(e) => setFormData((f) => ({ ...f, serviceAccount: e.target.value }))}
                placeholder="name@project.iam.gserviceaccount.com"
              />
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-bold text-gray-500 uppercase">Status</label>
              <Input
                value={formData.status}
                onChange={(e) => setFormData((f) => ({ ...f, status: e.target.value }))}
                placeholder="BigQuery"
              />
            </div>
          </div>

          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="outline" onClick={() => setIsModalOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              className="bg-[#5c27fe] hover:bg-[#4b1fd1]"
              onClick={handleSave}
              disabled={!formData.name.trim() || !formData.projectId.trim()}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="min-h-[200px] bg-white rounded-xl border p-6">
        <DestinationsStep variant="browse" />
      </div>
    </div>
  )
}
