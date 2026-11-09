import { motion, useReducedMotion } from "motion/react"

import { useI18n } from "@/i18n"
import { RISK_CRIT, RISK_WARN, levelVar, riskLevel } from "@/lib/levels"
import { motionTokens } from "@/lib/motion"
import { num } from "@/lib/format"
import { cn } from "@/lib/utils"

// The Fibo signature: a ruler with two threshold ticks. Same drawing for the risk index (0..1)
// everywhere, so a mechanic learns one scale.
export function RiskBar({
  value,
  className,
  showValue = true,
  size = "sm",
}: {
  value: number | null
  className?: string
  showValue?: boolean
  size?: "sm" | "lg"
}) {
  const { t, lang } = useI18n()
  const reduce = useReducedMotion()
  const level = riskLevel(value)
  const fill = level ? levelVar[level] : "var(--muted-foreground)"
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <div
        role="meter"
        aria-label={t("risk.index")}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={value ?? undefined}
        className={cn("relative w-full min-w-16 rounded-full bg-surface", size === "lg" ? "h-2.5" : "h-1.5")}
      >
        {value !== null && (
          <motion.div
            className="absolute inset-y-0 left-0 w-full origin-left rounded-full"
            style={{ background: fill }}
            initial={{ scaleX: reduce ? value : 0 }}
            animate={{ scaleX: value }}
            transition={{ duration: motionTokens.duration.slow, ease: motionTokens.easing.smooth }}
          />
        )}
        {[RISK_WARN, RISK_CRIT].map((tick) => (
          <span
            key={tick}
            aria-hidden
            className={cn(
              "absolute w-px bg-foreground/25",
              size === "lg" ? "-top-1 -bottom-1" : "-top-0.5 -bottom-0.5"
            )}
            style={{ left: `${tick * 100}%` }}
          />
        ))}
      </div>
      {showValue && (
        <span className={cn("num shrink-0 text-right", size === "lg" ? "w-12 text-base" : "w-9 text-sm")}>
          {value === null ? "—" : num(value, 2, lang)}
        </span>
      )}
    </div>
  )
}
