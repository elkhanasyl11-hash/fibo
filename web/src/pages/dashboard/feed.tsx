import { AudioLinesIcon, CameraIcon, MessageSquareTextIcon, MicIcon } from "lucide-react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { useEffect, useState } from "react"
import { Link } from "react-router"

import { LevelDot } from "@/components/level"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useI18n } from "@/i18n"
import { ago } from "@/lib/format"
import { springs, motionTokens } from "@/lib/motion"
import type { Incident, Machine } from "@/lib/types"
import { cn } from "@/lib/utils"

const INPUT = { voice: MicIcon, audio: AudioLinesIcon, photo: CameraIcon, text: MessageSquareTextIcon }
const MAX_ROWS = 7
const TICK_MS = 30_000

// What operators sent from Telegram, newest first. The list refreshes with the incidents query
// (15 s); a new report slides in at the top.
export function EventFeed({ incidents, machines, pending }: { incidents: Incident[]; machines: Machine[]; pending: boolean }) {
  const { t, lang } = useI18n()
  const reduce = useReducedMotion()
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), TICK_MS)
    return () => clearInterval(id)
  }, [])
  const names = new Map(machines.map((m) => [m.id, m.name]))
  const rows = [...incidents].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, MAX_ROWS)
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle className="text-base font-medium">{t("feed.title")}</CardTitle>
        <CardDescription>{t("feed.lead")}</CardDescription>
      </CardHeader>
      <CardContent>
        {pending ? (
          <Skeleton className="h-40 w-full" />
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground text-pretty">{t("feed.empty")}</p>
        ) : (
          <ul className="flex flex-col">
            <AnimatePresence initial={false}>
              {rows.map((incident) => {
                const Icon = INPUT[incident.input_type] ?? MicIcon
                return (
                  <motion.li
                    key={incident.id}
                    layout={!reduce}
                    initial={{ opacity: 0, y: reduce ? 0 : -motionTokens.distance.sm }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={springs.gentle}
                    className="border-b last:border-b-0"
                  >
                    <Link to={`/app/machines/${incident.machine_id}`} className="grid grid-cols-[16px_minmax(0,1fr)_auto] items-start gap-3 py-2.5 text-sm hover:text-primary">
                      <Icon className="mt-0.5 size-4 text-muted-foreground" strokeWidth={1.75} />
                      <span className="flex min-w-0 flex-col gap-0.5">
                        <span className="flex items-center gap-2">
                          <LevelDot level={incident.level} />
                          <span className="truncate font-medium">{names.get(incident.machine_id) ?? `#${incident.machine_id}`}</span>
                          {incident.safety_triggered && <span className="shrink-0 text-xs text-crit">{t("inc.safety")}</span>}
                        </span>
                        <span className={cn("truncate text-xs text-muted-foreground", incident.status === "resolved" && "line-through decoration-muted-foreground/40")}>
                          {incident.verdict ?? incident.transcript ?? t(`inc.status.${incident.status}`)}
                        </span>
                      </span>
                      <span className="num text-xs whitespace-nowrap text-muted-foreground">{ago(incident.created_at, lang, now)}</span>
                    </Link>
                  </motion.li>
                )
              })}
            </AnimatePresence>
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
