import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  ArrowLeftIcon,
  CalendarClockIcon,
  ClipboardPenIcon,
  PencilIcon,
  RefreshCwIcon,
} from "lucide-react"
import { useState } from "react"
import { Link, useParams, useSearchParams } from "react-router"
import { toast } from "sonner"

import { Hint } from "@/components/hint"
import { LevelBadge } from "@/components/level"
import { PageHeader } from "@/components/page-header"
import { RiskBar } from "@/components/risk-bar"
import { SafetyBanner } from "@/components/safety-banner"
import { Button } from "@/components/ui/button"
import { MaintenanceDialog } from "@/components/maintenance-dialog"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
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
import { date, kzt, num, pct } from "@/lib/format"
import { riskLevel } from "@/lib/levels"
import {
  machineTitle,
  useIncidents,
  useMachineSummary,
  useProfiles,
  useReport,
} from "@/lib/queries"
import { useSession } from "@/lib/session"
import { MachineTelemetry } from "./machine/telemetry"
import { AdviceSheet } from "./machine/advice-sheet"
import { AudioPanel } from "./machine/audio-panel"
import { DocsTab } from "./machine/docs"
import { ParamsTab } from "./machine/params"
import { PhotosTab } from "./machine/photos"
import { MachineHistory } from "./machine/history"
import { SignalCoverage } from "./machine/coverage"
import { RiskExplanation } from "./machine/explain"
import { IncidentList } from "./machine/incidents"
import { ReadingDialog } from "./machine/reading-dialog"
import { WhatIf, type Scenario } from "./machine/what-if"

const CRITICALITY = { 1: "crit.1", 2: "crit.2", 3: "crit.3" } as const

export function MachinePage() {
  const { id } = useParams()
  const machineId = Number(id)
  const { t, lang } = useI18n()
  const { auth } = useSession()
  const client = useQueryClient()
  const summary = useMachineSummary(
    Number.isFinite(machineId) ? machineId : undefined
  )
  const incidents = useIncidents({ machine_id: machineId, limit: 100 })
  const profiles = useProfiles()
  const profile = profiles.data?.find((p) => p.id === auth?.workshop.profile)
  const [scenario, setScenario] = useState<Scenario>({
    maintenance: false,
    tool: false,
    load: null,
  })
  const [adviceOpen, setAdviceOpen] = useState(false)
  const [readingOpen, setReadingOpen] = useState(false)
  const [maintenanceOpen, setMaintenanceOpen] = useState(false)
  const [params, setParams] = useSearchParams()
  const tab = params.get("tab") ?? (params.get("page") ? "docs" : "overview")
  const report = useReport(auth?.workshop.id, 30)

  const recompute = useMutation({
    mutationFn: () =>
      api("/risk-scores/recompute", {
        method: "POST",
        json: { machine_id: machineId },
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["machine-summary", machineId] })
      client.invalidateQueries({ queryKey: ["ranking"] })
      client.invalidateQueries({ queryKey: ["risk-history"] })
      toast.success(t("dash.recomputed"))
    },
    onError: () => toast.error(t("common.error")),
  })

  if (summary.isPending) {
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-12 w-72" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }
  if (
    summary.isError ||
    !summary.data ||
    summary.data.machine.workshop_id !== auth?.workshop.id
  ) {
    return (
      <Empty className="border bg-card shadow-card">
        <EmptyHeader>
          <EmptyTitle>{t("machine.notFound")}</EmptyTitle>
        </EmptyHeader>
        <EmptyContent>
          <Button asChild variant="outline">
            <Link to="/app/machines">{t("nav.machines")}</Link>
          </Button>
        </EmptyContent>
      </Empty>
    )
  }

  const { machine, latest_risk: risk } = summary.data
  const all = incidents.data ?? []
  const safety = all.find((i) => i.safety_triggered && i.status === "open")
  const toolApplies = auth.workshop.profile === "metalworking"
  const own = report.data?.machines?.find((m) => m.machine_id === machine.id)

  return (
    <>
      <SafetyBanner open={Boolean(safety)} detail={safety?.verdict} />
      <div className="flex flex-col gap-4">
        <Link
          to="/app/machines"
          className="inline-flex w-fit items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeftIcon className="size-4" />
          {t("nav.machines")}
        </Link>
        <PageHeader
          meta={
            <>
              <span>{machineTitle(profiles.data, machine.type, lang)}</span>
              {machine.model && <span>· {machine.model}</span>}
              <span>· {t(CRITICALITY[machine.criticality as 1 | 2 | 3])}</span>
            </>
          }
          title={machine.name}
          actions={
            <>
              <Button onClick={() => setMaintenanceOpen(true)}>
                <CalendarClockIcon data-icon="inline-start" />
                {t("mnt.assign")}
              </Button>
              <Button variant="outline" onClick={() => setReadingOpen(true)}>
                <ClipboardPenIcon data-icon="inline-start" />
                {t("reading.add")}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                aria-label={t("dash.recompute")}
                onClick={() => recompute.mutate()}
                disabled={recompute.isPending}
              >
                {recompute.isPending ? <Spinner /> : <RefreshCwIcon />}
              </Button>
              <Button
                asChild
                variant="ghost"
                size="icon"
                aria-label={t("common.edit")}
              >
                <Link to={`/app/machines/${machine.id}/edit`}>
                  <PencilIcon />
                </Link>
              </Button>
            </>
          }
        />
      </div>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          {
            label: t("risk.index"),
            value: risk ? <RiskBar value={risk.risk_index} size="lg" /> : "—",
          },
          {
            label: t("table.level"),
            value: <LevelBadge level={riskLevel(risk?.risk_index)} />,
          },
          {
            label: t("table.loss"),
            value: <span className="num">{kzt(risk?.priority_kzt, lang)}</span>,
          },
          {
            label: t("mhist.mtbf"),
            value: (
              <span className="num">
                {own?.mtbf_hours
                  ? `${num(own.mtbf_hours, 0, lang)} ${t("unit.h")}`
                  : "—"}
              </span>
            ),
          },
        ].map((stat) => (
          <div
            key={stat.label}
            className="flex min-w-0 flex-col gap-2 rounded-lg border bg-card p-4 shadow-card"
          >
            <dt className="text-xs text-muted-foreground">{stat.label}</dt>
            <dd className="text-lg">{stat.value}</dd>
          </div>
        ))}
      </dl>

      <MachineTelemetry summary={summary.data} profile={profile} />

      <Tabs
        value={tab}
        onValueChange={(v) =>
          setParams(
            (p) => {
              const n = new URLSearchParams(p)
              n.set("tab", v)
              return n
            },
            { replace: true }
          )
        }
      >
        <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <TabsList className="w-max">
            {(
              [
                "overview",
                "params",
                "sound",
                "photo",
                "incidents",
                "docs",
              ] as const
            ).map((key) => (
              <TabsTrigger key={key} value={key} className="h-9 px-3">
                {t(`mtab.${key}`)}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
        <TabsContent value="overview" className="mt-6 flex flex-col gap-4">
          {!risk ? (
            <Empty className="border bg-card py-10 shadow-card">
              <EmptyHeader>
                <EmptyTitle>{t("machine.noRiskTitle")}</EmptyTitle>
                <EmptyDescription className="max-w-md">
                  {t("machine.noRisk")}
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent className="flex-row flex-wrap justify-center">
                <Button onClick={() => setReadingOpen(true)}>
                  {t("reading.add")}
                </Button>
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
            <div className="grid gap-4 lg:grid-cols-2">
              <WhatIf
                summary={summary.data}
                toolApplies={toolApplies}
                scenario={scenario}
                onScenario={setScenario}
                onAdvice={() => setAdviceOpen(true)}
              />
              <RiskExplanation score={risk} />
              <SignalCoverage summary={summary.data} />
              <Card>
                <CardHeader>
                  <CardTitle className="text-base font-medium">
                    {t("risk.index")}
                  </CardTitle>
                  <CardDescription className="num">
                    {risk.model_version && risk.model_version !== "none"
                      ? t("machine.computed", {
                          date: date(risk.computed_at, lang, true),
                          model: risk.model_version,
                        })
                      : t("machine.computedIndex", {
                          date: date(risk.computed_at, lang, true),
                        })}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-4">
                  <dl className="grid grid-cols-2 gap-4">
                    <div className="flex flex-col gap-1">
                      <dt className="flex items-center gap-1 text-sm text-muted-foreground">
                        {t("table.probability")}
                        <Hint text={t("hint.probability")} />
                      </dt>
                      <dd className="num display text-[28px] leading-none">
                        {pct(risk.failure_probability, lang)}
                      </dd>
                    </div>
                    <div className="flex flex-col gap-1">
                      <dt className="flex items-center gap-1 text-sm text-muted-foreground">
                        {t("table.priority")}
                        <Hint text={t("hint.priority")} />
                      </dt>
                      <dd className="num display text-[28px] leading-none">
                        {kzt(risk.priority_kzt, lang)}
                      </dd>
                    </div>
                  </dl>
                  {risk.is_anomaly && (
                    <p className="rounded-md bg-warn-soft px-3 py-2 text-sm text-warn">
                      {t("machine.anomaly")}
                    </p>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
          <MachineHistory
            machine={machine}
            current={risk?.risk_index ?? null}
          />
        </TabsContent>
        <TabsContent value="params" className="mt-6">
          <ParamsTab machine={machine} profile={profile} />
        </TabsContent>
        <TabsContent value="sound" className="mt-6">
          <AudioPanel incidents={all} />
        </TabsContent>
        <TabsContent value="photo" className="mt-6">
          <PhotosTab machineId={machine.id} incidents={all} />
        </TabsContent>
        <TabsContent value="incidents" className="mt-6">
          <IncidentList incidents={all} />
        </TabsContent>
        <TabsContent value="docs" className="mt-6">
          <DocsTab
            machineId={machine.id}
            initialPage={params.get("page") ? Number(params.get("page")) : null}
          />
        </TabsContent>
      </Tabs>

      <AdviceSheet
        machine={machine}
        open={adviceOpen}
        onOpenChange={setAdviceOpen}
        toolApplies={toolApplies}
        onApply={setScenario}
      />
      <ReadingDialog
        machine={machine}
        profile={profile}
        open={readingOpen}
        onOpenChange={setReadingOpen}
      />
      {maintenanceOpen && (
        <MaintenanceDialog
          machine={machine}
          open
          onOpenChange={setMaintenanceOpen}
        />
      )}
    </>
  )
}
