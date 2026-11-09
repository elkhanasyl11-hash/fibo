import { useEffect, useRef } from "react"
import { useNavigate } from "react-router"
import { toast } from "sonner"

import { useI18n } from "@/i18n"
import { useIncidents, useMachines } from "@/lib/queries"
import { useSession } from "@/lib/session"
import type { Incident } from "@/lib/types"

const BASE_TITLE = "Fibo — обслуживание оборудования"
const urgent = (i: Incident) => i.status === "open" && (i.safety_triggered || i.level === "critical")

// Watches the workshop's open incidents (refreshed every 15 s): a new critical or "stop the machine"
// incident pops a toast with a link, and the tab title shows how many urgent incidents are open.
// Incidents that were already open when the page loaded do not toast again.
export function CriticalWatcher() {
  const { auth } = useSession()
  const { t } = useI18n()
  const navigate = useNavigate()
  const incidents = useIncidents({ workshop_id: auth?.workshop.id, status: "open", limit: 100 })
  const machines = useMachines(auth?.workshop.id)
  const seen = useRef<Set<number> | null>(null)

  useEffect(() => {
    const list = incidents.data
    if (!list) return
    const open = list.filter(urgent)
    document.title = open.length > 0 ? `(${open.length}) ${BASE_TITLE}` : BASE_TITLE
    if (seen.current === null) {
      seen.current = new Set(open.map((i) => i.id))
      return
    }
    for (const incident of open) {
      if (seen.current.has(incident.id)) continue
      seen.current.add(incident.id)
      const machine = machines.data?.find((m) => m.id === incident.machine_id)?.name ?? `#${incident.machine_id}`
      toast.error(incident.safety_triggered ? t("alert.stop", { machine }) : t("alert.critical", { machine }), {
        description: incident.verdict ?? undefined,
        duration: 30_000,
        action: { label: t("alert.open"), onClick: () => navigate(`/app/machines/${incident.machine_id}`) },
      })
    }
  }, [incidents.data, machines.data, navigate, t])

  useEffect(() => () => void (document.title = BASE_TITLE), [])
  return null
}
