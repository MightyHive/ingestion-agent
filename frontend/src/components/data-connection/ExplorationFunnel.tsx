"use client"

import { cn } from "@/lib/utils"

export interface FunnelStep {
  n: number
  label: string
  canEnter: boolean
}

interface ExplorationFunnelProps {
  steps: FunnelStep[]
  currentStep: number
  onStepClick: (step: number) => void
}

export default function ExplorationFunnel({
  steps,
  currentStep,
  onStepClick,
}: ExplorationFunnelProps) {
  const progressPercent = (currentStep / steps.length) * 100

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        {steps.map((step, index) => {
          const isActive = currentStep === step.n
          const isComplete = currentStep > step.n
          const isLast = index === steps.length - 1

          return (
            <div key={step.n} className="flex flex-1 items-start gap-2 min-w-0">
              <button
                type="button"
                disabled={!step.canEnter}
                onClick={() => step.canEnter && onStepClick(step.n)}
                className={cn(
                  "flex flex-col items-center gap-2 flex-1 min-w-0 text-center transition-opacity",
                  step.canEnter ? "cursor-pointer" : "cursor-not-allowed opacity-40"
                )}
              >
                <div
                  className={cn(
                    "flex h-10 w-10 shrink-0 items-center justify-center rounded-full border-2 text-sm font-bold transition-colors",
                    isActive && "border-[#5c27fe] bg-[#5c27fe] text-white",
                    isComplete && !isActive && "border-emerald-500 bg-emerald-500 text-white",
                    !isActive && !isComplete && "border-gray-200 bg-white text-gray-500"
                  )}
                >
                  {isComplete && !isActive ? (
                    <span className="material-symbols-outlined text-lg">check</span>
                  ) : (
                    step.n
                  )}
                </div>
                <span
                  className={cn(
                    "text-xs font-semibold leading-tight px-1",
                    isActive ? "text-[#5c27fe]" : "text-gray-600"
                  )}
                >
                  {step.label}
                </span>
              </button>
              {!isLast && (
                <div
                  className={cn(
                    "hidden sm:block h-0.5 flex-1 mt-5 min-w-[24px]",
                    isComplete ? "bg-emerald-400" : "bg-gray-200"
                  )}
                  aria-hidden
                />
              )}
            </div>
          )
        })}
      </div>

      <div
        role="progressbar"
        className="h-2 bg-gray-200 rounded-full overflow-hidden"
        aria-valuenow={currentStep}
        aria-valuemin={1}
        aria-valuemax={steps.length}
      >
        <div
          className="h-full bg-[#5c27fe] transition-all duration-500 ease-out"
          style={{ width: `${progressPercent}%` }}
        />
      </div>
    </div>
  )
}
