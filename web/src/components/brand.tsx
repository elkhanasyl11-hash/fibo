import { cn } from "@/lib/utils"

// Original supplied Fibo artwork, clipped to its ribbon without modifying the image.
export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "relative inline-block size-8 shrink-0 overflow-hidden rounded-[4px] bg-[#00172e]",
        className
      )}
    >
      <img
        src="/images/fibo-logo.png"
        alt=""
        className="absolute max-w-none"
        style={{ width: "132px", height: "48px", left: "-22px", top: "-7px" }}
        width="2083"
        height="755"
      />
    </span>
  )
}

export function Brand({ className }: { className?: string }) {
  return (
    <span className={cn("brand flex items-center gap-2", className)}>
      <BrandMark />
      <span className="brand-wordmark text-[17px] font-semibold tracking-tight">
        Fibo
      </span>
    </span>
  )
}
