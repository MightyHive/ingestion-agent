import Image from "next/image"
import { cn } from "@/lib/utils"

const sizeClasses = {
  sm: "h-8 w-8 rounded-lg",
  md: "h-10 w-10 rounded-xl",
  lg: "h-14 w-14 rounded-2xl",
  xl: "h-20 w-20 rounded-2xl",
}

const imageSizes = {
  sm: 32,
  md: 40,
  lg: 56,
  xl: 80,
}

interface DestinationLogoProps {
  size?: keyof typeof sizeClasses
  className?: string
}

export default function DestinationLogo({ size = "md", className }: DestinationLogoProps) {
  return (
    <div
      className={cn(
        "relative flex shrink-0 items-center justify-center overflow-hidden bg-white shadow-sm",
        sizeClasses[size],
        className
      )}
      title="Google Cloud Platform"
    >
      <Image
        src="/logo-gcp.svg"
        alt="Google Cloud Platform"
        width={imageSizes[size]}
        height={imageSizes[size]}
        className="object-contain p-1"
      />
    </div>
  )
}
