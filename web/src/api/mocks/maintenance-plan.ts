// TODO backend: there is no maintenance-plan endpoint yet (docs/frontend-decisions.md, F6).
// Planned maintenance (date, assignee, comment) is kept in this browser only and labelled as such
// in the UI. Marking maintenance as done is real: PATCH /machines/{id} with last_maintenance_at.

export interface MaintenancePlan {
  machineId: number
  date: string // yyyy-mm-dd
  assignee: string
  comment: string
  createdAt: string
}

const KEY = "fibo.maintenance-plans"

function readAll(): Record<string, MaintenancePlan> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") as Record<string, MaintenancePlan>
  } catch {
    return {}
  }
}

export function getPlan(machineId: number): MaintenancePlan | null {
  return readAll()[String(machineId)] ?? null
}

export function savePlan(plan: MaintenancePlan): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...readAll(), [String(plan.machineId)]: plan }))
  } catch {
    // storage blocked: the plan lives until the page reloads
  }
}

export function clearPlan(machineId: number): void {
  const all = readAll()
  delete all[String(machineId)]
  try {
    localStorage.setItem(KEY, JSON.stringify(all))
  } catch {
    // ignore
  }
}
