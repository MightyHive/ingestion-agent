"use client"
import {useState} from "react"
import {Button} from "@/components/ui/button"
import ConnectionStep from "@/components/data-connection/ConnectionStep"
import SelectionStep from "@/components/data-connection/SelectionStep"
import TemplateStep from "@/components/data-connection/TemplateStep"


export default function DataConnectionPage() {
const [step, setStep] = useState(1)
const [formData, setFormData] = useState({
    step1: { platform: ""},
    step2: { columns: [] as string[]},
    step3: { isSaved: false}
})

const updateFormData = (stepKey: string, newData: any) => {
    setFormData((prev) => ({
      ...prev, // Mantenemos los otros pasos intactos
      [stepKey]: { ...prev[stepKey as keyof typeof formData], ...newData } // Actualizamos solo el paso actual
    }))
  }

const renderStep = () => {
    switch (step) {
        case 1: return <ConnectionStep data={formData.step1} onUpdate={(data: any) => updateFormData("step1", data)} />;
        case 2: return <SelectionStep data={formData.step2} onUpdate={(data: any) => updateFormData("step2", data)} />;
        case 3: return <TemplateStep data={formData} onUpdate={(val: any) => updateFormData("step3", val)} />;
        default: return null;
    }
}

return (
    <div className="space-y-8 p-6">
      {/*Stepper */}
      <div className="flex gap-4 mb-8">
        <div className={`p-2 ${step === 1 ? 'font-bold border-b-2 border-purple-500' : ''}`}>Step 1</div>
        <div className={`p-2 ${step === 2 ? 'font-bold border-b-2 border-purple-500' : ''}`}>Step 2</div>
        <div className={`p-2 ${step === 3 ? 'font-bold border-b-2 border-purple-500' : ''}`}>Step 3</div>
      </div>

      {/* Actual step */}
      <div className="min-h-[400px] bg-white rounded-xl border p-6">
        {renderStep()}
      </div>

      {/* Botones de control */}
      <div className="flex justify-between mt-8">
        <Button 
          variant="outline" 
          onClick={() => setStep(step - 1)} 
          disabled={step === 1} 
        >
          Back
        </Button>
        
        <Button 
          className="bg-[#5c27fe]" 
          onClick={() => setStep(step + 1)}
          disabled={step === 3} 
        >
          Next
        </Button>
      </div>
    </div>
  )
}