import type { ReactNode } from "react"

import { Hint } from "@/components/hint"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

export interface KpiChange {
  text: string
  tone: "good" | "bad" | "flat"
}

export function Kpi({
  label,
  value,
  hint,
  sub,
  change,
  loading,
  tone,
  glow,
}: {
  label: string
  value: ReactNode
  hint: string
  sub?: ReactNode
  change?: KpiChange | null
  loading?: boolean
  tone?: "crit" | "warn"
  glow?: boolean
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-3 rounded-lg border bg-card p-4 shadow-card sm:p-5", glow && "shadow-glow-crit")}>
      <div className="flex items-start gap-1 text-sm leading-snug text-muted-foreground">
        <span className="min-h-[2lh] text-pretty sm:min-h-0">{label}</span>
        <Hint text={hint} />
      </div>
      {loading ? (
        <Skeleton className="h-9 w-24" />
      ) : (
        <div
          className={cn(
            "num display text-[24px] leading-none break-words sm:text-[32px]",
            tone === "crit" && "text-crit",
            tone === "warn" && "text-warn"
          )}
        >
          {value}
        </div>
      )}
      <div className="flex flex-col gap-0.5 text-xs text-pretty">
        {change && (
          <span
            className={cn(
              "num",
              change.tone === "good" && "text-ok",
              change.tone === "bad" && "text-crit",
              change.tone === "flat" && "text-muted-foreground"
            )}
          >
            {change.text}
          </span>
        )}
        {sub && <span className="text-muted-foreground">{sub}</span>}
      </div>
    </div>
  )
}
