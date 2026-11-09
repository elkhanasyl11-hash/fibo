import { CircleCheckIcon, CircleDashedIcon, ClockAlertIcon } from "lucide-react"

import { Hint } from "@/components/hint"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useI18n } from "@/i18n"
import { daysAgo } from "@/lib/format"
import type { MachineSummary } from "@/lib/types"

const STALE_DAYS = 7

// Which inputs the last risk computation used, which are missing, and which are older than a week.
export function SignalCoverage({ summary }: { summary: MachineSummary }) {
  const { t } = useI18n()
  const score = summary.latest_risk
  const used: string[] = []
  const missing: string[] = []
  const stale: string[] = []
  for (const signal of score?.signals ?? []) {
    if (signal.weight === 0) continue
    if (signal.value === null) missing.push(signal.title_ru)
    else used.push(signal.title_ru)
  }
  const lastReading = summary.recent_readings[0]
  const readingAge = daysAgo(lastReading?.recorded_at)
  if (!lastReading) missing.push(t("cov.readings"))
  else if (readingAge !== null && readingAge > STALE_DAYS) stale.push(t("cov.readingsAge", { n: readingAge }))
  if (!summary.machine.last_maintenance_at) missing.push(t("cov.maintenanceDate"))
  const groups = [
    { title: t("cov.used"), items: used, icon: CircleCheckIcon, tone: "text-ok" },
    { title: t("cov.missing"), items: missing, icon: CircleDashedIcon, tone: "text-muted-foreground" },
    { title: t("cov.stale"), items: stale, icon: ClockAlertIcon, tone: "text-warn" },
  ]
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1 text-base font-medium">
          {t("cov.title")}
          <Hint text={t("hint.coverage")} />
        </CardTitle>
        <CardDescription>{t("cov.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-5 sm:grid-cols-3">
        {groups.map(({ title, items, icon: Icon, tone }) => (
          <section key={title} className="flex flex-col gap-2.5">
            <h3 className="flex items-center gap-2 text-sm">
              <Icon className={`size-4 ${tone}`} strokeWidth={1.75} />
              {title}
              <span className="num text-muted-foreground">{items.length}</span>
            </h3>
            {items.length === 0 ? (
              <p className="text-sm text-muted-foreground">—</p>
            ) : (
              <ul className="flex flex-col gap-1.5 text-sm text-muted-foreground">
                {items.map((item) => (
                  <li key={item} className="text-pretty">
                    {item}
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </CardContent>
    </Card>
  )
}
