import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { Area, AreaChart, CartesianGrid, ReferenceLine, XAxis, YAxis } from "recharts"

import { Hint } from "@/components/hint"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Skeleton } from "@/components/ui/skeleton"
import { useI18n } from "@/i18n"
import { date, kzt, num } from "@/lib/format"
import { RISK_CRIT, RISK_WARN } from "@/lib/levels"
import { riskHistoryQuery, useReport } from "@/lib/queries"
import { DAY, scoreAt } from "@/lib/stats"
import type { Machine, RiskScore } from "@/lib/types"
import { cn } from "@/lib/utils"

function Delta({ label, now, before }: { label: string; now: number | null; before: RiskScore | null }) {
  const { lang } = useI18n()
  const diff = now !== null && before ? now - before.risk_index : null
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={cn("num text-lg", diff === null ? "text-muted-foreground" : diff < -0.005 ? "text-ok" : diff > 0.005 ? "text-crit" : "")}>
        {diff === null ? "—" : `${diff > 0 ? "+" : diff < 0 ? "−" : ""}${num(Math.abs(diff), 2, lang)}`}
      </dd>
    </div>
  )
}

// The machine's own trend: daily risk index for 30 days with the last maintenance marked, and the
// figures that show whether it is getting better: change over 7 / 30 days, incidents, downtime, MTBF.
export function MachineHistory({ machine, current }: { machine: Machine; current: number | null }) {
  const { t, lang } = useI18n()
  const [now] = useState(() => Date.now())
  const history = useQuery(riskHistoryQuery(machine.id, 30))
  const report = useReport(machine.workshop_id, 30)
  const own = report.data?.machines?.find((m) => m.machine_id === machine.id)
  const scores = history.data ?? []
  const data = scores.map((s) => ({ at: new Date(s.computed_at).getTime(), risk: s.risk_index }))
  const maintenance = machine.last_maintenance_at ? new Date(machine.last_maintenance_at).getTime() : null
  const showMaintenance = maintenance !== null && data.length > 0 && maintenance >= data[0].at
  const config = { risk: { label: t("risk.index"), color: "var(--chart-1)" } } satisfies ChartConfig
  const stat = (label: string, value: string, sub?: string) => (
    <div className="flex flex-col gap-1">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="num text-lg">{value}</dd>
      {sub && <dd className="text-xs text-muted-foreground">{sub}</dd>}
    </div>
  )
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle className="flex items-center gap-1 text-base font-medium">
          {t("mhist.title")}
          <Hint text={t("hint.mhist")} />
        </CardTitle>
        <CardDescription>{t("mhist.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-6 lg:grid-cols-[1fr_260px]">
        {history.isPending ? (
          <Skeleton className="h-56 w-full" />
        ) : data.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("chart.empty")}</p>
        ) : (
          <ChartContainer config={config} className="h-56 w-full">
            <AreaChart data={data} margin={{ left: 0, right: 8, top: 16, bottom: 0 }}>
              <CartesianGrid vertical={false} strokeDasharray="2 4" />
              <XAxis dataKey="at" type="number" scale="time" domain={["dataMin", "dataMax"]} tickLine={false} axisLine={false} tickMargin={8} minTickGap={40} tickFormatter={(v) => date(new Date(v).toISOString(), lang)} />
              <YAxis domain={[0, 1]} ticks={[0, RISK_WARN, RISK_CRIT, 1]} tickLine={false} axisLine={false} width={32} tickFormatter={(v) => num(v, 1, lang)} />
              <ReferenceLine y={RISK_CRIT} stroke="var(--crit)" strokeOpacity={0.4} strokeDasharray="4 4" />
              <ReferenceLine y={RISK_WARN} stroke="var(--warn)" strokeOpacity={0.4} strokeDasharray="4 4" />
              {showMaintenance && (
                <ReferenceLine x={maintenance!} stroke="var(--ok)" strokeOpacity={0.7} label={{ value: t("mhist.maintenance"), position: "insideTopLeft", fill: "var(--ok)", fontSize: 11 }} />
              )}
              <ChartTooltip
                cursor={{ stroke: "var(--border)" }}
                content={
                  <ChartTooltipContent
                    labelFormatter={(_, payload) => date(new Date(payload?.[0]?.payload?.at ?? 0).toISOString(), lang)}
                    formatter={(value) => (
                      <span className="num flex w-full justify-between gap-4">
                        <span className="text-muted-foreground">{t("risk.index")}</span>
                        {num(Number(value), 2, lang)}
                      </span>
                    )}
                  />
                }
              />
              <Area dataKey="risk" type="monotone" stroke="var(--color-risk)" strokeWidth={2} fill="var(--color-risk)" fillOpacity={0.08} dot={data.length < 8 ? { r: 3, fill: "var(--color-risk)", strokeWidth: 0 } : false} animationDuration={700} />
            </AreaChart>
          </ChartContainer>
        )}
        <dl className="grid grid-cols-2 content-start gap-x-4 gap-y-5">
          <Delta label={t("mhist.d7")} now={current} before={scoreAt(scores, now - 7 * DAY)} />
          <Delta label={t("mhist.d30")} now={current} before={scores[0] ?? null} />
          {stat(t("mhist.incidents"), own ? num(own.incidents) : "—", own ? t("mhist.failures", { n: own.failures }) : undefined)}
          {stat(t("mhist.downtime"), own ? `${num(own.downtime_hours + own.ongoing_hours, 1, lang)} ${t("unit.h")}` : "—")}
          {stat(t("mhist.mtbf"), own?.mtbf_hours ? `${num(own.mtbf_hours, 0, lang)} ${t("unit.h")}` : "—")}
          {stat(t("mhist.loss"), own ? kzt(Number(own.loss_kzt) + Number(own.ongoing_loss_kzt), lang) : "—")}
        </dl>
      </CardContent>
    </Card>
  )
}
