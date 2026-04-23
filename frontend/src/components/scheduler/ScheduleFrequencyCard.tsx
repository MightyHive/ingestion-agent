"use client"

import { useConnectorStore } from "@/lib/stores/connectorStore"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input" 
import { Label } from "@/components/ui/label"

export default function ScheduleFrequencyCard() {
  const { scheduleConfig, setScheduleConfig, templateProposal } = useConnectorStore()

  const config = scheduleConfig || { frequency: "daily", time: "00:00", isReady: false }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>Schedule for: {templateProposal?.tableName || "raw_table"}</CardTitle>
        <CardDescription>Configure frequency and execution time</CardDescription>
      </CardHeader>
      
      <CardContent className="space-y-6">
        {/* 1. Botones de Frecuencia */}
        <div className="flex flex-wrap gap-2">
          {["hourly", "daily", "weekly", "monthly"].map((f) => (
            <Button
              key={f}
              variant={config.frequency === f ? "default" : "outline"}
              onClick={() => setScheduleConfig({ frequency: f as any })}
              className="capitalize"
            >
              {f}
            </Button>
          ))}
        </div>

        {/* 2. Campo de Tiempo (Editable) */}
        <div className="flex items-center gap-4">
          <div className="grid w-full max-w-sm items-center gap-1.5">
            <Label htmlFor="time">Execution Time</Label>
            <Input 
              type="time" 
              id="time" 
              value={config.time} 
              onChange={(e) => setScheduleConfig({ time: e.target.value })}
            />
          </div>
        </div>

        {/* 3. El Combo Especial: Checkbox + READY Badge */}
        <div className="pt-4 border-t flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Checkbox 
              id="ready" 
              checked={config.isReady}
              onCheckedChange={(checked) => setScheduleConfig({ isReady: !!checked })}
            />
            <Label htmlFor="ready" className="cursor-pointer">Confirm Configuration</Label>
          </div>

          {/* Si está marcado, aparece el Badge */}
          {config.isReady && (
            <Badge className="bg-green-100 text-green-700 border-green-200 animate-in fade-in zoom-in duration-300">
              READY FOR DEPLOYMENT
            </Badge>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

