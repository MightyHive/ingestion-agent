"use client"
import { useCallback, useState } from "react"
import { Button } from "@/components/ui/button"
import ConnectionStep from "@/components/data-connection/ConnectionStep"
import SelectionStep from "@/components/data-connection/SelectionStep"
import TemplateStep from "@/components/data-connection/TemplateStep"

export default function DataConnectionPage() {
  const [step, setStep] = useState(1)
  const [formData, setFormData] = useState({
    step1: { platform: "" },
    step2: {
      columns: [] as string[],
      reportingLevel: null as string | null,
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

  const renderStep = () => {
    switch (step) {
      case 1:
        return (
          <ConnectionStep
            data={formData.step1}
            onUpdate={onStep1Update}
          />
        )
      case 2:
        return (
          <SelectionStep
            data={formData.step2}
            onUpdate={onStep2Update}
          />
        )
      case 3:
        return (
          <TemplateStep
            data={formData}
            onUpdate={onStep3Update}
          />
        )
      default:
        return null
    }
  }

  const progressPercent = (step / 3) * 100

  const step2Completed =
    formData.step2.columns.length > 0 && formData.step2.reportingLevel !== null

  const STEPS = [
    { n: 1, label: "Connection", canEnter: true },
    { n: 2, label: "Selectors", canEnter: true },
    { n: 3, label: "Template", canEnter: step2Completed },
  ] as const

  return (
    <div className="space-y-8 p-6">
      <div className="flex gap-4 mb-8 items-center">
        {STEPS.map(({ n, label, canEnter }) => (
          <div
            key={n}
            onClick={() => canEnter && setStep(n)}
            className={`p-2 text-sm transition-colors ${
              canEnter ? "cursor-pointer hover:text-purple-600" : "cursor-not-allowed opacity-40"
            } ${step === n ? "font-bold border-b-2 border-purple-500" : ""}`}
          >
            {label}
          </div>
        ))}
        <div
          role="progressbar"
          className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden"
        >
          <div
            className="h-full bg-[#5c27fe] transition-all duration-500 ease-out"
            style={{ width: `${progressPercent}%` }}
            aria-valuenow={step}
            aria-valuemin={1}
            aria-valuemax={3}
          />
        </div>
      </div>

      <div className="min-h-[400px] bg-white rounded-xl border p-6">
        {renderStep()}
      </div>

      <div
        className={`mt-8 flex ${
          step > 1 && step < 3
            ? "justify-between"
            : step === 1
              ? "justify-end"
              : "justify-start"
        }`}
      >
        {step > 1 && (
          <Button variant="outline" onClick={() => setStep(step - 1)}>
            Back
          </Button>
        )}
        {step < 3 && (
          <Button
            className="bg-[#5c27fe]"
            onClick={() => setStep(step + 1)}
            disabled={step === 2 && !step2Completed}
          >
            Next
          </Button>
        )}
      </div>
    </div>
  )
}
