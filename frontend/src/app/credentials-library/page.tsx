"use client"

import { useState, useEffect } from "react"
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter } from "@/components/ui/dialog"
import { generateCredentialId } from "@/lib/generateCredentialId"
import {cn} from "@/lib/utils"
import { useCredentialStore } from "@/lib/stores/credentialStore"

export default function CredentialsPage() {
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null) // Para saber si estamos editando
  const { credentials, addCredential, updateCredential, deleteCredential} = useCredentialStore()


  // 2. Estado para capturar los datos del formulario
  const [formData, setFormData] = useState({
    name: "",
    platform: "META",
    market: "",
    brand: "",
    token: ""
  })

// Función para abrir modal en modo "Crear"
const openCreateModal = () => {
  setEditingId(null)
  setFormData({ name: "", platform: "META", market: "", brand: "", token: "" })
  setIsModalOpen(true)
}

// Función para abrir modal en modo "Editar"
const openEditModal = (conn: any) => {
  setEditingId(conn.id)
  setFormData({
    name: conn.name,
    platform: conn.platform,
    market: conn.market,
    brand: conn.brand,
    token: conn.token || ""
  })
  setIsModalOpen(true)
}

    // Guardar (Crear o Editar)
    const handleSave = () => {
      const entry = {
        ...formData,
        id: editingId || generateCredentialId(formData.platform, formData.brand, formData.market),
        status: "Healthy",
        owner: "You (Admin)"
      }
      if (editingId) {
        updateCredential(editingId, entry)}
        else { addCredential(entry)}
      setIsModalOpen(false)
    }

    // Eliminar
    const handleDelete = (id: string) => {
      if (confirm("Are you sure you want to delete this connection?")) {
        deleteCredential(id)
      }
    }
    // Simulación TEST API
    const handleTest = (id: string) => {
      // 1. Buscamos la credencial actual en el Store
      const currentCred = credentials.find(c => c.id === id)
      if (!currentCred) return
    
      // 2. Cambiamos estado a "Testing..." usando la función del Store
      updateCredential(id, { ...currentCred, status: "Testing..." })
    
      // 3. Simulamos delay de red (2 segundos)
      setTimeout(() => {
        const updatedCred = credentials.find(c => c.id === id)
        if (updatedCred) {
          updateCredential(id, { ...updatedCred, status: "Healthy" })
        }
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
          <DialogTrigger>
            <div className="inline-flex items-center justify-center bg-[#5c27fe] hover:bg-[#4b1fd1] text-white h-10 px-4 py-2 rounded-md cursor-pointer transition-colors font-medium">
              <span className="material-symbols-outlined mr-2 text-[20px]">add</span>
              Add Connection
            </div>
          </DialogTrigger>

          <DialogContent className="bg-white sm:max-w-[425px]">
            <DialogHeader>
              <DialogTitle className="text-xl font-bold">Add New Credential</DialogTitle>
            </DialogHeader>
            
            <div className="grid gap-4 py-4">
              <div className="space-y-2">
                <label className="text-[10px] font-bold text-gray-500 uppercase">Connection Name</label>
                <Input 
                  placeholder="e.g. Meta France Cadillac" 
                  value={formData.name}
                  onChange={(e) => setFormData({...formData, name: e.target.value})}
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-[10px] font-bold text-gray-500 uppercase">Platform</label>
                  <select 
                    className="w-full p-2 border rounded-md bg-white text-sm"
                    value={formData.platform}
                    onChange={(e) => setFormData({...formData, platform: e.target.value})}
                  >
                    <option value="META">Meta</option>
                    <option value="TIKTOK">TikTok</option>
                    <option value="YOUTUBE">YouTube</option>
                    <option value="CM360">CM360</option>
                    <option value="GOOGLE ADS">Google</option>
                    <option value="DV360">Snapchat</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] font-bold text-gray-500 uppercase">Market</label>
                  <Input 
                    placeholder="e.g. France" 
                    value={formData.market}
                    onChange={(e) => setFormData({...formData, market: e.target.value})}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-bold text-gray-500 uppercase">Brand</label>
                <Input 
                  placeholder="e.g. Cadillac" 
                  value={formData.brand}
                  onChange={(e) => setFormData({...formData, brand: e.target.value})}
                />
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-bold text-gray-500 uppercase">Access Token</label>
                <Input 
                  type="password" 
                  placeholder="••••••••••••" 
                  value={formData.token}
                  onChange={(e) => setFormData({...formData, token: e.target.value})}
                />
              </div>
              
              {/* Preview del ID que se va a generar */}
              <div className="p-3 bg-slate-50 rounded-lg border border-dashed border-slate-200">
                <p className="text-[9px] font-bold text-slate-400 uppercase mb-1">Generated ID Preview</p>
                <code className="text-xs font-mono text-purple-600">
                  {formData.brand && formData.market ? generateCredentialId(formData.platform, formData.brand, formData.market) : "waiting for data..."}
                </code>
              </div>
            </div>

            <DialogFooter className="gap-2">
              {editingId && (
                <Button variant="destructive" className="mr-auto" onClick={() => { handleDelete(editingId); setIsModalOpen(false); }}>
                  Delete
                </Button>
              )}
              <Button variant="outline" onClick={() => setIsModalOpen(false)}>Cancel</Button>
              <Button className="bg-[#5c27fe] text-white" onClick={handleSave}>
                {editingId ? "Update" : "Save Connection"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      {/* Stats Cards - Ahora dinámicas según el largo de la lista */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard title="TOTAL CONNECTIONS" value={credentials.length} icon="key" />
        <StatCard title="HEALTHY" value={credentials.length} icon="check_circle" color="text-green-500" />
        <StatCard title="ACTION NEEDED" value="0" icon="warning" color="text-orange-500" />
        <StatCard title="MARKETS COVERED" value="--" icon="public" />
      </div>

      {/* Search and Filters */}
      <div className="flex gap-4 items-center bg-white p-2 rounded-full border border-gray-100 shadow-sm">
        <div className="relative flex-1">
          <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">search</span>
          <Input className="pl-12 border-none bg-transparent focus-visible:ring-0 shadow-none" placeholder="Search connections or markets..." />
        </div>
        <div className="flex gap-2 pr-2">
          {["All", "Meta", "TikTok", "YouTube", "CM360"].map(p => (
            <Button key={p} variant="ghost" className="rounded-full px-4 h-8 text-sm font-medium">{p}</Button>
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
            {/* 4. Mapeamos el estado para que la tabla sea dinámica */}
            {credentials.map((conn) => (
              <TableRow key={conn.id}>
                <TableCell>
                  <div className="font-medium text-gray-900">{conn.name}</div>
                  <div className="text-[11px] text-gray-400 font-mono">{conn.id}</div>
                </TableCell>
                <TableCell>
                  <Badge variant="secondary" className="bg-gray-100 text-gray-600 border-none font-bold uppercase">{conn.platform}</Badge>
                </TableCell>
                <TableCell className="text-gray-600 font-medium">{conn.market}</TableCell>
                <TableCell className="text-gray-600 font-medium">{conn.brand}</TableCell>
                <TableCell>
                  <div className={cn(
                    "flex items-center gap-1 font-medium text-sm",
                    conn.status === "Testing..." ? "text-blue-500" : "text-green-600"
                  )}>
                    <span className={cn(
                      "material-symbols-outlined text-[18px]",
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
                    <Button variant="ghost" size="sm" className="text-gray-400" onClick={() => openEditModal(conn)}>
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
            ))}
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