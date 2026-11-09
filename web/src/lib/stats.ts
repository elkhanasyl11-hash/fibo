// Workshop statistics computed from data the backend already returns (risk histories, ranking).
// Nothing here is estimated by AI: every figure is a stored risk computation or a sum of them.

import { dayKey } from "./format"
import { RISK_CRIT, RISK_WARN } from "./levels"
import type { RankingItem, RiskScore } from "./types"

export const DAY = 86_400_000
export type Histories = Map<number, RiskScore[]> // machine id -> scores, oldest first

/** The latest score computed at or before `time` (risk persists until the next computation). */
export function scoreAt(history: RiskScore[] | undefined, time: number): RiskScore | null {
  let found: RiskScore | null = null
  for (const score of history ?? []) {
    if (new Date(score.computed_at).getTime() > time) break
    found = score
  }
  return found
}

export interface DayPoint {
  day: string // yyyy-mm-dd
  at: number // end of that day (or now for today)
  lossKzt: number | null // sum of priority_kzt over machines known that day
  avgRisk: number | null
  machines: number // machines with a score by that day
  byMachine: { id: number; name: string; kzt: number; risk: number }[]
}

/** One point per day: each machine's last known score by the end of the day, summed. */
export function dailySeries(items: RankingItem[], histories: Histories, days: number, now: number): DayPoint[] {
  const points: DayPoint[] = []
  for (let i = days - 1; i >= 0; i--) {
    const end = i === 0 ? now : new Date(new Date(now - i * DAY).setHours(23, 59, 59, 999)).getTime()
    const byMachine = items.flatMap((item) => {
      const score = scoreAt(histories.get(item.machine_id), end)
      return score
        ? [{ id: item.machine_id, name: item.machine_name, kzt: Number(score.priority_kzt), risk: score.risk_index }]
        : []
    })
    const total = byMachine.reduce((sum, m) => sum + m.kzt, 0)
    points.push({
      day: dayKey(new Date(end)),
      at: end,
      lossKzt: byMachine.length ? total : null,
      avgRisk: byMachine.length ? byMachine.reduce((s, m) => s + m.risk, 0) / byMachine.length : null,
      machines: byMachine.length,
      byMachine: byMachine.sort((a, b) => b.kzt - a.kzt),
    })
  }
  return points
}

export interface Mover {
  id: number
  name: string
  now: number
  before: number | null // null: no score that long ago
  delta: number | null
  nowKzt: number
  deltaKzt: number | null
}

/** Risk change of every machine over `period` ms, biggest change first. */
export function movers(items: RankingItem[], histories: Histories, period: number, now: number): Mover[] {
  return items
    .map((item) => {
      const before = scoreAt(histories.get(item.machine_id), now - period)
      const nowKzt = Number(item.score.priority_kzt)
      return {
        id: item.machine_id,
        name: item.machine_name,
        now: item.score.risk_index,
        before: before?.risk_index ?? null,
        delta: before ? item.score.risk_index - before.risk_index : null,
        nowKzt,
        deltaKzt: before ? nowKzt - Number(before.priority_kzt) : null,
      }
    })
    .sort((a, b) => Math.abs(b.delta ?? 0) - Math.abs(a.delta ?? 0))
}

/** Workshop totals a week ago, for the KPI comparisons. Null when no machine had a score then. */
export function totalsAt(items: RankingItem[], histories: Histories, time: number) {
  const scores = items.map((i) => scoreAt(histories.get(i.machine_id), time)).filter((s): s is RiskScore => s !== null)
  if (scores.length === 0) return null
  return {
    atRisk: scores.filter((s) => s.risk_index >= RISK_WARN).length,
    red: scores.filter((s) => s.risk_index >= RISK_CRIT).length,
    avgRisk: scores.reduce((sum, s) => sum + s.risk_index, 0) / scores.length,
    lossKzt: scores.reduce((sum, s) => sum + Number(s.priority_kzt), 0),
  }
}
