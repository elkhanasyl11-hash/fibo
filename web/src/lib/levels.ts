import type { Level } from "./types"

// Risk-index bands used by the dashboard to colour a 0..1 index. The backend stores the index
// itself; these cut-offs are a display choice and are explained next to the legend.
export const RISK_WARN = 0.3
export const RISK_CRIT = 0.6

// Machine-sound thresholds of the backend (settings.audio_z_warning / audio_z_critical).
export const SIGMA_WARN = 2
export const SIGMA_CRIT = 3

export function riskLevel(index: number | null | undefined): Level | null {
  if (index === null || index === undefined) return null
  if (index >= RISK_CRIT) return "critical"
  if (index >= RISK_WARN) return "warning"
  return "normal"
}

export const levelVar: Record<Level, string> = {
  normal: "var(--ok)",
  warning: "var(--warn)",
  critical: "var(--crit)",
}
