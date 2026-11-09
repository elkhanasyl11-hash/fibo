import type { RiskScore } from "@/lib/types"

// The factor that pushes the risk up the most: the top SHAP factor when the failure model ran,
// otherwise the risk-index signal with the largest weighted value.
export function mainFactor(score: RiskScore): string | null {
  const shap = score.shap_top3.find((f) => f.contribution > 0)
  if (shap) return shap.title_ru
  const signals = score.signals
    .filter((s) => s.value !== null && s.value > 0)
    .sort((a, b) => (b.value ?? 0) * b.weight - (a.value ?? 0) * a.weight)
  return signals[0]?.title_ru ?? null
}
