import { useMutation, useQueryClient } from "@tanstack/react-query"
import { PlusIcon, RefreshCwIcon } from "lucide-react"
import { motion, useReducedMotion } from "motion/react"
import { useState, type ReactNode } from "react"
import { Link } from "react-router"
import { toast } from "sonner"

import { EChartsContributionsHeatmapChart } from "@/components/evilcharts/blocks/contributions-echarts-heatmap-chart"
import { EChartsMarketSharePieChart } from "@/components/evilcharts/blocks/market-share-echarts-pie-chart"
import { AnimatedNumber } from "@/components/animated-number"
import { Kpi, type KpiChange } from "@/components/kpi"
import { LiveStatus } from "@/components/live-status"
import { PageHeader } from "@/components/page-header"
import { SafetyBanner } from "@/components/safety-banner"
import { TelegramConnect } from "@/components/telegram-connect"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { useI18n } from "@/i18n"
import { api } from "@/lib/api"
import { kzt, num } from "@/lib/format"
import { RISK_CRIT } from "@/lib/levels"
import { motionTokens } from "@/lib/motion"
import {
  useActivity,
  useHistories,
  useIncidents,
  useMachines,
  useRanking,
  useReport,
} from "@/lib/queries"
import { useSession } from "@/lib/session"
import { DAY, totalsAt } from "@/lib/stats"
import { TopCauses } from "./dashboard/causes"
import { EventFeed } from "./dashboard/feed"
import { RiskHeatmap } from "./dashboard/heatmap"
import { Movers } from "./dashboard/movers"
import { PriorityTable } from "./dashboard/priority-table"
import { Recommendation } from "./dashboard/recommendation"
import { WorkshopChart } from "./dashboard/workshop-chart"

// One short fade-and-rise for the page sections on first load, 50 ms apart.
function Reveal({
  index,
  children,
  className,
}: {
  index: number
  children: ReactNode
  className?: string
}) {
  const reduce = useReducedMotion()
  return (
    <motion.section
      className={className}
      initial={{ opacity: 0, y: reduce ? 0 : motionTokens.distance.sm }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: motionTokens.duration.normal,
        ease: motionTokens.easing.smooth,
        delay: Math.min(index, 6) * 0.05,
      }}
    >
      {children}
    </motion.section>
  )
}

function change(
  now: number,
  before: number | null | undefined,
  lowerIsBetter: boolean,
  format: (v: number) => string
): KpiChange | null {
  if (before === null || before === undefined) return null
  const diff = now - before
  if (Math.abs(diff) < 1e-9) return { text: format(0), tone: "flat" }
  const good = lowerIsBetter ? diff < 0 : diff > 0
  return { text: format(diff), tone: good ? "good" : "bad" }
}

export function DashboardPage() {
  const { t, lang } = useI18n()
  const { auth } = useSession()
  const workshopId = auth?.workshop.id
  const client = useQueryClient()
  const [now] = useState(() => Date.now())
  const machines = useMachines(workshopId)
  const ranking = useRanking(workshopId)
  const incidents = useIncidents({ workshop_id: workshopId, limit: 200 })
  const report = useReport(workshopId, 30)
  const activity = useActivity(workshopId)
  const items = ranking.data?.items ?? []
  const { histories, pending: historyPending } = useHistories(
    items.map((i) => i.machine_id)
  )

  const recompute = useMutation({
    mutationFn: () =>
      api("/risk-scores/recompute", {
        method: "POST",
        json: { workshop_id: workshopId },
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["ranking"] })
      client.invalidateQueries({ queryKey: ["risk-history"] })
      toast.success(t("dash.recomputed"))
    },
    onError: () => toast.error(t("common.error")),
  })

  if (!auth) return null
  const all = incidents.data ?? []
  const open = all.filter(
    (i) =>
      i.status === "open" ||
      i.status === "processing" ||
      i.status === "received"
  )
  const critical = open.filter((i) => i.level === "critical").length
  const safety = open.find((i) => i.safety_triggered)
  const red = items.filter((i) => i.score.risk_index >= RISK_CRIT).length
  const avgRisk = items.length
    ? items.reduce((s, i) => s + i.score.risk_index, 0) / items.length
    : null
  const expected = items.reduce(
    (sum, i) => sum + Number(i.score.priority_kzt),
    0
  )
  const weekAgo = historyPending
    ? null
    : totalsAt(items, histories, now - 7 * DAY)
  const newThisWeek = all.filter(
    (i) => new Date(i.created_at).getTime() >= now - 7 * DAY
  ).length
  const noMachines = machines.isSuccess && machines.data.length === 0
  const unscored = ranking.data?.unscored_machine_ids.length ?? 0
  const signed = (v: number, f: (x: number) => string) =>
    `${v > 0 ? "+" : v < 0 ? "−" : ""}${f(Math.abs(v))}`

  return (
    <>
      <SafetyBanner
        open={Boolean(safety)}
        detail={
          safety
            ? t("safety.on", {
                machine:
                  items.find((i) => i.machine_id === safety.machine_id)
                    ?.machine_name ?? `#${safety.machine_id}`,
              })
            : null
        }
      />
      <PageHeader
        meta={
          <>
            <span>{t("dash.meta", { city: auth.workshop.city })}</span>
            <span aria-hidden>·</span>
            <LiveStatus
              updatedAt={ranking.dataUpdatedAt}
              fetching={ranking.isFetching}
            />
          </>
        }
        title={auth.workshop.name}
        description={t("dash.lead")}
        actions={
          !noMachines && (
            <>
              <Button
                variant="outline"
                onClick={() => recompute.mutate()}
                disabled={recompute.isPending}
              >
                {recompute.isPending ? (
                  <Spinner data-icon="inline-start" />
                ) : (
                  <RefreshCwIcon data-icon="inline-start" />
                )}
                {t("dash.recompute")}
              </Button>
              <Button asChild>
                <Link to="/app/machines/new">
                  <PlusIcon data-icon="inline-start" />
                  {t("machines.add")}
                </Link>
              </Button>
            </>
          )
        }
      />

      {(machines.isError || ranking.isError) && (
        <Alert variant="destructive">
          <AlertTitle>
            {lang === "kk"
              ? "Деректер жүктелмеді"
              : "Не удалось загрузить данные"}
          </AlertTitle>
          <AlertDescription>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                machines.refetch()
                ranking.refetch()
              }}
            >
              {t("common.retry")}
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {noMachines ? (
        <div className="flex flex-col gap-6">
          <Empty className="border bg-card py-12 shadow-card">
            <EmptyHeader>
              <EmptyTitle className="display text-2xl">
                {t("dash.emptyTitle")}
              </EmptyTitle>
              <EmptyDescription className="max-w-md">
                {t("dash.empty")}
              </EmptyDescription>
            </EmptyHeader>
            <EmptyContent>
              <Button asChild size="lg">
                <Link to="/app/machines/new">
                  <PlusIcon data-icon="inline-start" />
                  {t("machines.addFirst")}
                </Link>
              </Button>
            </EmptyContent>
          </Empty>
          <TelegramConnect
            link={auth.telegram_link}
            inviteCode={auth.workshop.invite_code}
          />
        </div>
      ) : (
        <>
          <Reveal
            index={0}
            className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4"
          >
            <Kpi
              label={t("kpi.red")}
              hint={t("hint.red")}
              loading={ranking.isPending}
              value={
                <AnimatedNumber
                  value={red}
                  format={(v) => num(Math.round(v))}
                />
              }
              tone={red > 0 ? "crit" : undefined}
              change={change(red, weekAgo?.red, true, (d) =>
                t("kpi.vsWeek", { v: signed(d, (x) => num(x)) })
              )}
              sub={t("kpi.ofMachines", { n: machines.data?.length ?? 0 })}
            />
            <Kpi
              label={t("kpi.expected")}
              hint={t("hint.expected")}
              loading={ranking.isPending}
              value={
                <AnimatedNumber value={expected} format={(v) => kzt(v, lang)} />
              }
              change={change(expected, weekAgo?.lossKzt, true, (d) =>
                t("kpi.vsWeek", { v: signed(d, (x) => kzt(x, lang)) })
              )}
              sub={t("kpi.expectedSub")}
            />
            <Kpi
              label={t("kpi.avgRisk")}
              hint={t("hint.avgRisk")}
              loading={ranking.isPending}
              value={
                avgRisk === null ? (
                  "—"
                ) : (
                  <AnimatedNumber
                    value={avgRisk}
                    format={(v) => num(v, 2, lang)}
                  />
                )
              }
              change={
                avgRisk === null
                  ? null
                  : change(avgRisk, weekAgo?.avgRisk, true, (d) =>
                      t("kpi.vsWeek", { v: signed(d, (x) => num(x, 2, lang)) })
                    )
              }
              sub={t("kpi.avgRiskSub")}
            />
            <Kpi
              label={t("kpi.open")}
              hint={t("hint.open")}
              loading={incidents.isPending}
              value={
                <AnimatedNumber
                  value={open.length}
                  format={(v) => num(Math.round(v))}
                />
              }
              tone={critical > 0 ? "crit" : undefined}
              change={{
                text: t("kpi.newWeek", { n: newThisWeek }),
                tone: "flat",
              }}
              sub={
                critical > 0
                  ? t("kpi.critical", { n: critical })
                  : t("kpi.noCritical")
              }
            />
          </Reveal>

          <Reveal
            index={1}
            className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]"
          >
            <Card className="min-w-0">
              <CardContent className="pt-6">
                <EChartsContributionsHeatmapChart
                  activity={activity.data}
                  loading={activity.isPending}
                />
                {activity.isError && (
                  <p role="alert" className="mt-4 text-sm text-destructive">
                    {lang === "kk"
                      ? "Белсенділік деректері қолжетімсіз"
                      : "Данные активности недоступны"}
                    <Button variant="link" onClick={() => activity.refetch()}>
                      {t("common.retry")}
                    </Button>
                  </p>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardContent className="pt-6">
                <EChartsMarketSharePieChart
                  machines={machines.data ?? []}
                  ranking={items}
                />
              </CardContent>
            </Card>
          </Reveal>

          {items.length > 0 && (
            <Reveal index={1} className="grid gap-4 xl:grid-cols-3">
              <div className="min-w-0 xl:col-span-2">
                <WorkshopChart
                  items={items}
                  histories={histories}
                  pending={historyPending}
                />
              </div>
              <Recommendation top={items[0]} />
            </Reveal>
          )}

          <Reveal index={2}>
            <Card>
              <CardHeader>
                <CardTitle className="text-base font-medium">
                  {t("table.title")}
                </CardTitle>
                <CardDescription>{t("table.lead")}</CardDescription>
              </CardHeader>
              <CardContent>
                {ranking.isPending ? (
                  <div className="flex flex-col gap-3">
                    {[0, 1, 2].map((i) => (
                      <Skeleton key={i} className="h-12 w-full" />
                    ))}
                  </div>
                ) : items.length === 0 ? (
                  <Empty className="border border-dashed">
                    <EmptyHeader>
                      <EmptyTitle>{t("table.emptyTitle")}</EmptyTitle>
                      <EmptyDescription>{t("table.empty")}</EmptyDescription>
                    </EmptyHeader>
                    <EmptyContent>
                      <Button
                        variant="outline"
                        onClick={() => recompute.mutate()}
                        disabled={recompute.isPending}
                      >
                        {t("dash.recompute")}
                      </Button>
                    </EmptyContent>
                  </Empty>
                ) : (
                  <PriorityTable items={items} machines={machines.data ?? []} />
                )}
                {unscored > 0 && items.length > 0 && (
                  <p className="mt-4 text-sm text-muted-foreground">
                    {t("table.unscored", { n: unscored })}
                  </p>
                )}
              </CardContent>
            </Card>
          </Reveal>

          {items.length > 0 && (
            <Reveal
              index={3}
              className="grid gap-4 lg:grid-cols-2 2xl:grid-cols-3"
            >
              <Movers
                items={items}
                histories={histories}
                pending={historyPending}
                now={now}
              />
              <TopCauses report={report.data} pending={report.isPending} />
              <div className="lg:col-span-2 2xl:col-span-1">
                <EventFeed
                  incidents={all}
                  machines={machines.data ?? []}
                  pending={incidents.isPending}
                />
              </div>
            </Reveal>
          )}

          {items.length > 0 && (
            <Reveal index={4}>
              <RiskHeatmap items={items} />
            </Reveal>
          )}
        </>
      )}
    </>
  )
}
