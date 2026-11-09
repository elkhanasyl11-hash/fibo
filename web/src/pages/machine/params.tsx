import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { CartesianGrid, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts"

import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { useI18n, type Key } from "@/i18n"
import { api, query } from "@/lib/api"
import { date, num } from "@/lib/format"
import { DAY_MS } from "@/lib/queries"
import type { Machine, ProfileConfig, Reading } from "@/lib/types"

const BASE: { name: keyof Reading; label: Key; unit: string }[] = [
  { name: "load_pct", label: "field.load_pct", unit: "%" },
  { name: "temperature_c", label: "field.temperature_c", unit: "°C" },
  { name: "spindle_rpm", label: "field.spindle_rpm", unit: "об/мин" },
  { name: "operating_hours", label: "field.operating_hours", unit: "ч" },
]

// Reading history per parameter (7/30/90 days). The dashed line is the upper bound of the
// profile's valid range (values above it are rejected by the backend).
export function ParamsTab({ machine, profile }: { machine: Machine; profile: ProfileConfig | undefined }) {
  const { t, lang } = useI18n()
  const [days, setDays] = useState(30)
  const readings = useQuery({
    queryKey: ["readings", machine.id, days],
    queryFn: () => {
      const from = new Date(Date.now() - days * DAY_MS).toISOString()
      return api<Reading[]>(`/machines/${machine.id}/readings${query({ from, limit: 200 })}`)
    },
  })
  const rows = [...(readings.data ?? [])].reverse()
  const extra = (profile?.extra_fields ?? []).map((f) => ({ name: f.name, label: (lang === "kk" && f.title_kk) || f.title_ru, unit: f.unit }))
  const series = [
    ...BASE.map((b) => ({ name: b.name as string, label: t(b.label), unit: b.unit })),
    ...extra,
  ].filter((s) => rows.some((r) => (s.name in r ? r[s.name as keyof Reading] : r.extra?.[s.name]) != null))
  const value = (r: Reading, name: string) => (name in r ? (r[name as keyof Reading] as number | null) : (r.extra?.[name] ?? null))

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-medium">{t("params.title")}</CardTitle>
        <CardDescription>{t("params.lead")}</CardDescription>
        <CardAction>
          <ToggleGroup type="single" size="sm" variant="outline" value={String(days)} onValueChange={(v) => v && setDays(Number(v))}>
            {[7, 30, 90].map((d) => (
              <ToggleGroupItem key={d} value={String(d)} className="num px-2.5 text-xs">{d} {t("wchart.d")}</ToggleGroupItem>
            ))}
          </ToggleGroup>
        </CardAction>
      </CardHeader>
      <CardContent>
        {readings.isPending ? (
          <Skeleton className="h-56 w-full" />
        ) : series.length === 0 ? (
          <Empty className="border border-dashed">
            <EmptyHeader>
              <EmptyTitle>{t("params.emptyTitle")}</EmptyTitle>
              <EmptyDescription>{t("params.empty")}</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <div className="grid gap-6 lg:grid-cols-2">
            {series.map((s) => {
              const config = { v: { label: s.label, color: "var(--chart-1)" } } satisfies ChartConfig
              const data = rows.map((r) => ({ at: new Date(r.recorded_at).getTime(), v: value(r, s.name) })).filter((d) => d.v !== null)
              const limit = profile?.reading_ranges[s.name]?.[1]
              const latest = data.at(-1)?.v
              return (
                <section key={s.name} className="flex flex-col gap-2">
                  <div className="flex items-baseline justify-between gap-2">
                    <h3 className="text-sm text-muted-foreground">{s.label}</h3>
                    <span className="num text-lg">{latest == null ? "—" : `${num(latest, 1, lang)} ${s.unit}`}</span>
                  </div>
                  <ChartContainer config={config} className="h-40 w-full">
                    <LineChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
                      <CartesianGrid vertical={false} strokeDasharray="2 4" />
                      <XAxis dataKey="at" type="number" scale="time" domain={["dataMin", "dataMax"]} tickLine={false} axisLine={false} minTickGap={40} tickFormatter={(v) => date(new Date(v).toISOString(), lang)} />
                      <YAxis tickLine={false} axisLine={false} width={44} tickFormatter={(v) => num(v, 0, lang)} />
                      {limit !== undefined && <ReferenceLine y={limit} stroke="var(--crit)" strokeOpacity={0.5} strokeDasharray="4 4" />}
                      <ChartTooltip
                        content={
                          <ChartTooltipContent
                            labelFormatter={(_, p) => date(new Date(p?.[0]?.payload?.at ?? 0).toISOString(), lang, true)}
                            formatter={(v) => <span className="num">{num(Number(v), 1, lang)} {s.unit}</span>}
                          />
                        }
                      />
                      <Line dataKey="v" type="monotone" stroke="var(--color-v)" strokeWidth={2} dot={data.length < 12} />
                    </LineChart>
                  </ChartContainer>
                </section>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
