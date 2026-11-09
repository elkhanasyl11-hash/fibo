import { useState } from "react"
import { Area, AreaChart, CartesianGrid, ReferenceLine, XAxis, YAxis } from "recharts"

import { AnimatedNumber } from "@/components/animated-number"
import { Hint } from "@/components/hint"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart"
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { useI18n } from "@/i18n"
import { date, kzt, kztShort, num } from "@/lib/format"
import { RISK_CRIT, RISK_WARN } from "@/lib/levels"
import { dailySeries, type DayPoint, type Histories } from "@/lib/stats"
import type { RankingItem } from "@/lib/types"
import { cn } from "@/lib/utils"

type Metric = "loss" | "risk"

function TooltipBody({ point, metric }: { point: DayPoint; metric: Metric }) {
  const { t, lang } = useI18n()
  return (
    <div className="flex min-w-48 flex-col gap-2 rounded-md border bg-popover px-3 py-2.5 text-xs shadow-float">
      <span className="text-muted-foreground">{date(new Date(point.at).toISOString(), lang)}</span>
      <span className="num text-sm font-medium">
        {metric === "loss" ? kzt(point.lossKzt, lang) : num(point.avgRisk, 2, lang)}
      </span>
      <ul className="flex flex-col gap-1">
        {point.byMachine.slice(0, 4).map((m) => (
          <li key={m.id} className="flex justify-between gap-4 text-muted-foreground">
            <span className="truncate">{m.name}</span>
            <span className="num text-foreground">{metric === "loss" ? kztShort(m.kzt, lang) : num(m.risk, 2, lang)}</span>
          </li>
        ))}
      </ul>
      {point.machines > 4 && <span className="text-muted-foreground">{t("wchart.more", { n: point.machines - 4 })}</span>}
    </div>
  )
}

// The main chart of the overview: the whole workshop's expected losses (or average risk index) per
// day. Each day takes every machine's last stored risk computation; nothing is interpolated by AI.
export function WorkshopChart({ items, histories, pending }: { items: RankingItem[]; histories: Histories; pending: boolean }) {
  const { t, lang } = useI18n()
  const [metric, setMetric] = useState<Metric>("loss")
  const [days, setDays] = useState(30)
  const [now] = useState(() => Date.now())
  const series = dailySeries(items, histories, days, now).filter((p) => p.lossKzt !== null)
  const first = series[0]
  const last = series.at(-1)
  const value = (p: DayPoint | undefined) => (p ? (metric === "loss" ? (p.lossKzt ?? 0) : (p.avgRisk ?? 0)) : 0)
  const change = first && last && series.length > 1 && value(first) > 0 ? (value(last) - value(first)) / value(first) : null
  const config = { value: { label: metric === "loss" ? t("wchart.loss") : t("wchart.risk"), color: "var(--chart-1)" } } satisfies ChartConfig
  const data = series.map((p) => ({ at: p.at, value: value(p), point: p }))

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle className="flex items-center gap-1 text-base font-medium">
          {metric === "loss" ? t("wchart.titleLoss") : t("wchart.titleRisk")}
          <Hint text={t("hint.wchart")} />
        </CardTitle>
        <CardDescription className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="display text-[32px] leading-none text-foreground">
            <AnimatedNumber value={value(last)} format={(v) => (metric === "loss" ? kzt(v, lang) : num(v, 2, lang))} />
          </span>
          {change !== null && (
            <span className={cn("num text-sm", change <= 0 ? "text-ok" : "text-crit")}>
              {change > 0 ? "+" : "−"}
              {num(Math.abs(change) * 100, 0, lang)}% {t("wchart.since", { date: date(new Date(first!.at).toISOString(), lang) })}
            </span>
          )}
        </CardDescription>
        <CardAction className="flex flex-col items-end gap-2 sm:flex-row sm:items-center">
          <ToggleGroup type="single" size="sm" variant="outline" value={metric} onValueChange={(v) => v && setMetric(v as Metric)}>
            <ToggleGroupItem value="loss" className="px-2.5 text-xs">₸</ToggleGroupItem>
            <ToggleGroupItem value="risk" className="px-2.5 text-xs">{t("wchart.riskShort")}</ToggleGroupItem>
          </ToggleGroup>
          <ToggleGroup type="single" size="sm" variant="outline" value={String(days)} onValueChange={(v) => v && setDays(Number(v))}>
            <ToggleGroupItem value="7" className="num px-2.5 text-xs">7 {t("wchart.d")}</ToggleGroupItem>
            <ToggleGroupItem value="30" className="num px-2.5 text-xs">30 {t("wchart.d")}</ToggleGroupItem>
          </ToggleGroup>
        </CardAction>
      </CardHeader>
      <CardContent>
        {pending ? (
          <Skeleton className="h-72 w-full" />
        ) : data.length < 2 ? (
          <Empty className="h-72 border border-dashed">
            <EmptyHeader>
              <EmptyTitle>{data.length === 0 ? t("chart.emptyTitle") : t("wchart.oneDayTitle")}</EmptyTitle>
              <EmptyDescription>{data.length === 0 ? t("chart.empty") : t("wchart.oneDay")}</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <ChartContainer config={config} className="h-72 w-full">
            <AreaChart data={data} margin={{ left: 0, right: 8, top: 12, bottom: 0 }}>
              <CartesianGrid vertical={false} strokeDasharray="2 4" />
              <XAxis
                dataKey="at"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={40}
                tickFormatter={(v) => date(new Date(v).toISOString(), lang)}
              />
              <YAxis
                tickLine={false}
                axisLine={false}
                width={64}
                domain={metric === "risk" ? [0, 1] : [0, "auto"]}
                tickFormatter={(v) => (metric === "loss" ? kztShort(v, lang).replace(" ₸", "").replace(" ", "\u00a0") : num(v, 1, lang))}
              />
              {metric === "risk" && (
                <>
                  <ReferenceLine y={RISK_CRIT} stroke="var(--crit)" strokeOpacity={0.4} strokeDasharray="4 4" />
                  <ReferenceLine y={RISK_WARN} stroke="var(--warn)" strokeOpacity={0.4} strokeDasharray="4 4" />
                </>
              )}
              <ChartTooltip
                cursor={{ stroke: "var(--border)" }}
                content={({ payload }) => (payload?.[0] ? <TooltipBody point={payload[0].payload.point} metric={metric} /> : null)}
              />
              <Area
                dataKey="value"
                type="monotone"
                stroke="var(--color-value)"
                strokeWidth={2}
                fill="var(--color-value)"
                fillOpacity={0.08}
                dot={data.length < 8 ? { r: 3, fill: "var(--color-value)", strokeWidth: 0 } : false}
                activeDot={{ r: 4 }}
                animationDuration={700}
              />
            </AreaChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}
