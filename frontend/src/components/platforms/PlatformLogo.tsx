import { getCredentialPlatform } from "@/lib/platforms/credential-platforms"
import { cn } from "@/lib/utils"

const sizeClasses = {
  sm: "h-8 w-8 text-xs rounded-lg",
  md: "h-10 w-10 text-sm rounded-xl",
  lg: "h-14 w-14 text-lg rounded-2xl",
  xl: "h-20 w-20 text-2xl rounded-2xl",
}

interface PlatformLogoProps {
  platform: string
  size?: keyof typeof sizeClasses
  className?: string
}

export default function PlatformLogo({ platform, size = "md", className }: PlatformLogoProps) {
  const config = getCredentialPlatform(platform)

  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center font-bold text-white shadow-sm",
        sizeClasses[size],
        className
      )}
      style={{ backgroundColor: config.color }}
      title={config.label}
      aria-hidden
    >
      {config.initial}
    </div>
  )
}
