import { useQueries } from "@tanstack/react-query"
import { useState } from "react"
import { Link } from "react-router"

import { Hint } from "@/components/hint"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useI18n } from "@/i18n"
import { date, dayKey, num } from "@/lib/format"
import { levelVar, riskLevel } from "@/lib/levels"
import { DAY_MS, riskHistoryQuery } from "@/lib/queries"
import type { RankingItem } from "@/lib/types"

const DAYS = 30

// Machines × days: the highest risk index of each day. Empty cell = no computation that day.
export function RiskHeatmap({ items }: { items: RankingItem[] }) {
  const { t, lang } = useI18n()
  const histories = useQueries({ queries: items.map((item) => riskHistoryQuery(item.machine_id, DAYS)) })
  const [now] = useState(() => Date.now())
  const days = Array.from({ length: DAYS }, (_, i) => new Date(now - (DAYS - 1 - i) * DAY_MS))
  const loading = histories.some((h) => h.isPending)
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle className="flex items-center gap-1 text-base font-medium">
          {t("heat.title")}
          <Hint text={t("hint.heat")} />
        </CardTitle>
        <CardDescription>{t("heat.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {loading ? (
          <Skeleton className="h-32 w-full" />
        ) : (
          <div className="overflow-x-auto pb-1">
            <div className="grid min-w-[520px] items-center gap-x-3 gap-y-1.5" style={{ gridTemplateColumns: "minmax(88px, 140px) 1fr" }}>
              {items.map((item, row) => {
                const byDay = new Map<string, number>()
                for (const score of histories[row].data ?? []) {
                  const key = dayKey(score.computed_at)
                  byDay.set(key, Math.max(byDay.get(key) ?? 0, score.risk_index))
                }
                return [
                  <Link key={`n${item.machine_id}`} to={`/app/machines/${item.machine_id}`} className="truncate text-sm hover:text-primary">
                    {item.machine_name}
                  </Link>,
                  <div key={`r${item.machine_id}`} className="grid gap-[3px]" style={{ gridTemplateColumns: `repeat(${DAYS}, minmax(0, 1fr))` }}>
                    {days.map((day) => {
                      const value = byDay.get(dayKey(day))
                      const level = riskLevel(value)
                      return (
                        <Tooltip key={day.toISOString()}>
                          <TooltipTrigger asChild>
                            <span
                              tabIndex={0}
                              aria-label={`${item.machine_name}, ${date(day.toISOString(), lang)}: ${value === undefined ? t("heat.noData") : num(value, 2, lang)}`}
                              className="aspect-square rounded-[3px] bg-foreground/[0.07] outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              style={level ? { background: levelVar[level], opacity: 0.35 + (value ?? 0) * 0.65 } : undefined}
                            />
                          </TooltipTrigger>
                          <TooltipContent>
                            <span className="num">
                              {date(day.toISOString(), lang)} · {value === undefined ? t("heat.noData") : num(value, 2, lang)}
                            </span>
                          </TooltipContent>
                        </Tooltip>
                      )
                    })}
                  </div>,
                ]
              })}
              <span />
              <div className="flex justify-between text-xs text-muted-foreground">
                <span className="num">{date(days[0].toISOString(), lang)}</span>
                <span>{t("heat.today")}</span>
              </div>
            </div>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
          {(["normal", "warning", "critical"] as const).map((level) => (
            <span key={level} className="inline-flex items-center gap-1.5">
              <span className="size-2.5 rounded-[3px]" style={{ background: levelVar[level] }} />
              {t(`level.${level}`)}
            </span>
          ))}
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-[3px] bg-foreground/[0.07]" />
            {t("heat.noData")}
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
