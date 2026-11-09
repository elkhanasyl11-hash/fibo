import { motion, useReducedMotion } from "motion/react"
import { Link } from "react-router"

import { Hint } from "@/components/hint"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useI18n } from "@/i18n"
import { kztShort, num } from "@/lib/format"
import { motionTokens } from "@/lib/motion"
import { DAY, movers, type Histories } from "@/lib/stats"
import type { RankingItem } from "@/lib/types"
import { cn } from "@/lib/utils"

const STEADY = 0.02 // a change of the risk index below this counts as "no change"
const MAX_ROWS = 6

// How each machine's risk moved over the last 7 days: a diverging bar around zero, green when it
// improved (after maintenance, a fixed incident) and red when it got worse.
export function Movers({ items, histories, pending, now }: { items: RankingItem[]; histories: Histories; pending: boolean; now: number }) {
  const { t, lang } = useI18n()
  const reduce = useReducedMotion()
  const rows = movers(items, histories, 7 * DAY, now)
  const known = rows.filter((r) => r.delta !== null)
  const better = known.filter((r) => (r.delta ?? 0) <= -STEADY).length
  const worse = known.filter((r) => (r.delta ?? 0) >= STEADY).length
  const scale = Math.max(...known.map((r) => Math.abs(r.delta ?? 0)), 0.1)
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle className="flex items-center gap-1 text-base font-medium">
          {t("mov.title")}
          <Hint text={t("hint.movers")} />
        </CardTitle>
        <CardDescription>
          {known.length ? t("mov.summary", { better, worse, same: known.length - better - worse }) : t("mov.lead")}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {pending ? (
          <Skeleton className="h-40 w-full" />
        ) : known.length === 0 ? (
          <p className="text-sm text-muted-foreground text-pretty">{t("mov.empty")}</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {known.slice(0, MAX_ROWS).map((row, i) => {
              const delta = row.delta ?? 0
              const width = `${(Math.min(Math.abs(delta), scale) / scale) * 50}%`
              const improved = delta <= -STEADY
              const worsened = delta >= STEADY
              return (
                <li key={row.id}>
                  <Link to={`/app/machines/${row.id}`} className="grid grid-cols-[minmax(0,1fr)_88px_52px] items-center gap-3 text-sm hover:text-primary">
                    <span className="flex min-w-0 flex-col">
                      <span className="truncate">{row.name}</span>
                      <span className="num text-xs text-muted-foreground">
                        {num(row.before, 2, lang)} → {num(row.now, 2, lang)}
                        {row.deltaKzt !== null && Math.abs(row.deltaKzt) >= 1 && (
                          <> · {row.deltaKzt > 0 ? "+" : "−"}{kztShort(Math.abs(row.deltaKzt), lang)}</>
                        )}
                      </span>
                    </span>
                    <span className="relative h-2 rounded-full bg-surface" aria-hidden>
                      <span className="absolute inset-y-[-3px] left-1/2 w-px bg-foreground/25" />
                      <motion.span
                        className={cn("absolute inset-y-0 rounded-full", improved ? "right-1/2 bg-ok" : worsened ? "left-1/2 bg-crit" : "left-1/2 bg-muted-foreground")}
                        style={{ width, originX: improved ? 1 : 0 }}
                        initial={{ scaleX: reduce ? 1 : 0 }}
                        animate={{ scaleX: 1 }}
                        transition={{ duration: motionTokens.duration.slow, ease: motionTokens.easing.smooth, delay: i * motionTokens.stagger }}
                      />
                    </span>
                    <span className={cn("num text-right", improved ? "text-ok" : worsened ? "text-crit" : "text-muted-foreground")}>
                      {Math.abs(delta) < STEADY ? "0" : `${delta > 0 ? "+" : "−"}${num(Math.abs(delta), 2, lang)}`}
                    </span>
                  </Link>
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
