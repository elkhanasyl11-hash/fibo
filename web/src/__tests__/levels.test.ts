import { describe, expect, it } from "vitest"

import { RISK_CRIT, RISK_WARN, riskLevel } from "@/lib/levels"
import { movers, scoreAt, totalsAt } from "@/lib/stats"
import type { RankingItem, RiskScore } from "@/lib/types"

function score(
  machineId: number,
  at: string,
  risk: number,
  kztValue = 1000
): RiskScore {
  return {
    id: 1,
    machine_id: machineId,
    computed_at: at,
    failure_probability: null,
    risk_index: risk,
    priority_kzt: String(kztValue),
    is_anomaly: false,
    inputs_used: [],
    model_version: "none",
    is_demo: false,
    shap_top3: [],
    signals: [],
    assumptions: [],
    model_not_used_reasons: [],
    anomaly_reason: null,
  }
}

describe("risk levels", () => {
  it("maps the index to the three levels at the thresholds", () => {
    expect(riskLevel(null)).toBeNull()
    expect(riskLevel(0)).toBe("normal")
    expect(riskLevel(RISK_WARN)).toBe("warning")
    expect(riskLevel(RISK_CRIT - 0.001)).toBe("warning")
    expect(riskLevel(RISK_CRIT)).toBe("critical")
  })
})

describe("workshop statistics", () => {
  const history = [
    score(1, "2026-11-01T10:00:00Z", 0.2, 500),
    score(1, "2026-11-08T10:00:00Z", 0.7, 9000),
  ]
  const item: RankingItem = {
    machine_id: 1,
    machine_name: "ЧПУ-1",
    machine_type: "cnc_mill",
    criticality: 3,
    is_demo: false,
    score: history[1],
  }

  it("takes the last score at or before a moment", () => {
    expect(
      scoreAt(history, Date.parse("2026-11-05T00:00:00Z"))?.risk_index
    ).toBe(0.2)
    expect(scoreAt(history, Date.parse("2026-10-01T00:00:00Z"))).toBeNull()
  })

  it("computes the 7-day change and the totals a week ago", () => {
    const now = Date.parse("2026-11-09T00:00:00Z")
    const [m] = movers([item], new Map([[1, history]]), 7 * 86_400_000, now)
    expect(m.delta).toBeCloseTo(0.5)
    expect(m.deltaKzt).toBe(8500)
    expect(
      totalsAt([item], new Map([[1, history]]), now - 7 * 86_400_000)
    ).toMatchObject({ red: 0, lossKzt: 500 })
  })
})
