"use client"

import { useCallback, useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import ConnectionStep from "@/components/data-connection/ConnectionStep"
import ExplorationFunnel from "@/components/data-connection/ExplorationFunnel"
import ScopeFieldsStep from "@/components/data-connection/ScopeFieldsStep"
import TemplateStep from "@/components/data-connection/TemplateStep"
import TemplatesLibraryPanel from "@/components/templates/TemplatesLibraryPanel"

const TOTAL_STEPS = 3

export default function DataConnectionPage() {
  const [step, setStep] = useState(1)
  const [formData, setFormData] = useState({
    step1: { platform: "" },
    step2: {
      reportingLevel: null as string | null,
      columns: [] as string[],
    },
    step3: { isSaved: false },
  })

  const onStep1Update = useCallback((data: Record<string, unknown>) => {
    setFormData((prev) => ({ ...prev, step1: { ...prev.step1, ...data } }))
  }, [])

  const onStep2Update = useCallback((data: Record<string, unknown>) => {
    setFormData((prev) => ({ ...prev, step2: { ...prev.step2, ...data } }))
  }, [])

  const onStep3Update = useCallback((data: Record<string, unknown>) => {
    setFormData((prev) => ({ ...prev, step3: { ...prev.step3, ...data } }))
  }, [])

  const step1Completed = Boolean(formData.step1.platform)
  const step2Completed =
    formData.step2.reportingLevel !== null && formData.step2.columns.length > 0

  const FUNNEL_STEPS = [
    { n: 1, label: "Select Connector", canEnter: true },
    { n: 2, label: "Scope & Fields", canEnter: step1Completed },
    { n: 3, label: "Save Template", canEnter: step1Completed && step2Completed },
  ]

  const renderStep = () => {
    switch (step) {
      case 1:
        return <ConnectionStep data={formData.step1} onUpdate={onStep1Update} />
      case 2:
        return (
          <ScopeFieldsStep
            data={formData.step2}
            onUpdate={onStep2Update}
          />
        )
      case 3:
        return (
          <TemplateStep
            data={{
              step1: formData.step1,
              step2: {
                columns: formData.step2.columns,
                reportingLevel: formData.step2.reportingLevel,
              },
              step3: formData.step3,
            }}
            onUpdate={onStep3Update}
            onGoToStep={setStep}
          />
        )
      default:
        return null
    }
  }

  const canGoNext =
    (step === 1 && step1Completed) ||
    (step === 2 && step2Completed)

  useEffect(() => {
    if (typeof window === "undefined") return
    if (window.location.hash === "#templates") {
      setStep(1)
      requestAnimationFrame(() => {
        document.getElementById("templates")?.scrollIntoView({ behavior: "smooth", block: "start" })
      })
    }
  }, [])

  return (
    <div className="space-y-8 p-6">
      <div>
        <h1 className="text-2xl font-bold">Data Exploration</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Connect platforms, choose reporting scope, select fields, and save extraction templates.
        </p>
      </div>

      <ExplorationFunnel steps={FUNNEL_STEPS} currentStep={step} onStepClick={setStep} />

      <div className="min-h-[400px] bg-white rounded-xl border p-6">{renderStep()}</div>

      <div
        className={`mt-8 flex ${
          step > 1 && step < TOTAL_STEPS ? "justify-between" : step === 1 ? "justify-end" : "justify-start"
        }`}
      >
        {step > 1 && (
          <Button variant="outline" onClick={() => setStep(step - 1)}>
            Back
          </Button>
        )}
        {step < TOTAL_STEPS && (
          <Button className="bg-[#5c27fe]" onClick={() => setStep(step + 1)} disabled={!canGoNext}>
            Next
          </Button>
        )}
      </div>

      {step === 1 && (
        <section id="templates" className="rounded-xl border border-border bg-slate-50/50 p-6">
          <TemplatesLibraryPanel />
        </section>
      )}
    </div>
  )
}
