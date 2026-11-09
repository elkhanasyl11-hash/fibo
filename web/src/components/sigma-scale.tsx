import { motion, useReducedMotion } from "motion/react"

import { useI18n } from "@/i18n"
import { SIGMA_CRIT, SIGMA_WARN, levelVar } from "@/lib/levels"
import { motionTokens } from "@/lib/motion"
import { num } from "@/lib/format"

// How far the machine's sound is from its own healthy baseline, in sigmas, with the backend's
// thresholds (2σ attention, 3σ critical).
export function SigmaScale({ z }: { z: number }) {
  const { t, lang } = useI18n()
  const reduce = useReducedMotion()
  const max = Math.max(5, Math.ceil(z + 1))
  const at = (v: number) => `${(Math.min(v, max) / max) * 100}%`
  const level = z > SIGMA_CRIT ? "critical" : z >= SIGMA_WARN ? "warning" : "normal"
  return (
    <div className="flex flex-col gap-2">
      <div className="relative h-8">
        <div className="absolute inset-x-0 top-3 h-2 overflow-hidden rounded-full bg-surface">
          <span className="absolute inset-y-0 bg-warn-soft" style={{ left: at(SIGMA_WARN), width: `calc(${at(SIGMA_CRIT)} - ${at(SIGMA_WARN)})` }} />
          <span className="absolute inset-y-0 right-0 bg-crit-soft" style={{ left: at(SIGMA_CRIT) }} />
        </div>
        <motion.span
          aria-hidden
          className="absolute top-1.5 size-5 -translate-x-1/2 rounded-full border-2 border-card shadow-float"
          style={{ background: levelVar[level] }}
          initial={{ left: reduce ? at(z) : "0%" }}
          animate={{ left: at(z) }}
          transition={{ duration: motionTokens.duration.slow, ease: motionTokens.easing.smooth }}
        />
      </div>
      <div className="relative h-4 text-xs text-muted-foreground">
        {[0, SIGMA_WARN, SIGMA_CRIT, max].map((tick) => (
          <span key={tick} className="num absolute -translate-x-1/2" style={{ left: at(tick) }}>
            {tick}σ
          </span>
        ))}
      </div>
      <p className="text-sm text-muted-foreground">
        {t("audio.deviation", { z: num(z, 1, lang) })}
      </p>
    </div>
  )
}
