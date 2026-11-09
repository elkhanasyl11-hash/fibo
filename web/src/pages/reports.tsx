import { DownloadIcon, PrinterIcon } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router"

import { Kpi } from "@/components/kpi"
import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { useI18n } from "@/i18n"
import { query } from "@/lib/api"
import { date, kzt, num } from "@/lib/format"
import { DAY_MS, useReportRange } from "@/lib/queries"
import { useSession } from "@/lib/session"
import { TopCauses } from "./dashboard/causes"

// Fibo Reports: downtime, losses, MTBF and top causes for a period (GET /reports/summary),
// CSV for Excel (GET /reports/export.csv) and a printable page (browser "Save as PDF").
export function ReportsPage() {
  const { t, lang } = useI18n()
  const { auth } = useSession()
  const [days, setDays] = useState(30)
  const report = useReportRange(auth?.workshop.id, days, 0)
  const prev = useReportRange(auth?.workshop.id, days * 2, days)
  const data = report.data
  const totals = data?.totals
  const prevTotals = prev.data?.totals
  const [now] = useState(() => Date.now())
  const csv = `/api/v1/reports/export.csv${query({ workshop_id: auth?.workshop.id, from: new Date(now - days * DAY_MS).toISOString() })}`
  const downtime = totals ? totals.downtime_hours + totals.ongoing_hours : 0
  const loss = totals ? Number(totals.loss_kzt) + Number(totals.ongoing_loss_kzt) : 0
  const prevDowntime = prevTotals ? prevTotals.downtime_hours + prevTotals.ongoing_hours : null
  const prevLoss = prevTotals ? Number(prevTotals.loss_kzt) + Number(prevTotals.ongoing_loss_kzt) : null
  const cmp = (now: number, before: number | null, f: (v: number) => string) =>
    before === null ? null : { text: t("rep.vsPrev", { v: `${now - before > 0 ? "+" : now - before < 0 ? "−" : ""}${f(Math.abs(now - before))}` }), tone: now < before ? ("good" as const) : now > before ? ("bad" as const) : ("flat" as const) }

  return (
    <>
      <PageHeader
        title={t("rep.title")}
        description={data ? t("rep.period", { from: date(data.period_from, lang), to: date(data.period_to, lang) }) : t("rep.lead")}
        actions={
          <>
            <ToggleGroup type="single" size="sm" variant="outline" value={String(days)} onValueChange={(v) => v && setDays(Number(v))}>
              {[7, 30, 90].map((d) => <ToggleGroupItem key={d} value={String(d)} className="num h-9 px-3 text-xs">{d} {t("wchart.d")}</ToggleGroupItem>)}
            </ToggleGroup>
            <Button asChild variant="outline">
              <a href={csv} download>
                <DownloadIcon data-icon="inline-start" />
                CSV
              </a>
            </Button>
            <Button variant="outline" onClick={() => window.print()}>
              <PrinterIcon data-icon="inline-start" />
              PDF
            </Button>
          </>
        }
      />
      <div className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <Kpi label={t("rep.incidents")} hint={t("hint.repIncidents")} loading={report.isPending} value={num(totals?.incidents ?? 0)} sub={t("rep.failures", { n: totals?.failures ?? 0 })} />
        <Kpi label={t("kpi.downtime")} hint={t("hint.downtime")} loading={report.isPending} value={`${num(downtime, 1, lang)} ${t("unit.h")}`} change={cmp(downtime, prevDowntime, (v) => `${num(v, 1, lang)} ${t("unit.h")}`)} />
        <Kpi label={t("rep.loss")} hint={t("hint.repLoss")} loading={report.isPending} value={kzt(loss, lang)} change={cmp(loss, prevLoss, (v) => kzt(v, lang))} />
        <Kpi label={t("rep.ongoing")} hint={t("hint.repOngoing")} loading={report.isPending} value={`${num(totals?.ongoing_hours ?? 0, 1, lang)} ${t("unit.h")}`} tone={(totals?.ongoing_hours ?? 0) > 0 ? "crit" : undefined} />
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.6fr_1fr]">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle className="text-base font-medium">{t("rep.byMachine")}</CardTitle>
            <CardDescription>{t("rep.byMachineLead")}</CardDescription>
          </CardHeader>
          <CardContent>
            {report.isPending ? (
              <Skeleton className="h-48 w-full" />
            ) : !data?.machines?.length ? (
              <Empty className="border border-dashed"><EmptyHeader><EmptyTitle>{t("rep.emptyTitle")}</EmptyTitle><EmptyDescription>{t("rep.empty")}</EmptyDescription></EmptyHeader></Empty>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="hover:bg-transparent">
                      <TableHead>{t("table.machine")}</TableHead>
                      <TableHead className="text-right">{t("rep.incidents")}</TableHead>
                      <TableHead className="text-right">{t("kpi.downtime")}</TableHead>
                      <TableHead className="text-right">{t("rep.loss")}</TableHead>
                      <TableHead className="text-right">{t("mhist.mtbf")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {[...data.machines].sort((a, b) => Number(b.loss_kzt) + Number(b.ongoing_loss_kzt) - Number(a.loss_kzt) - Number(a.ongoing_loss_kzt)).map((m) => (
                      <TableRow key={m.machine_id} className="h-12">
                        <TableCell><Link to={`/app/machines/${m.machine_id}`} className="font-medium hover:text-primary">{m.machine}</Link></TableCell>
                        <TableCell className="num text-right">{num(m.incidents)} <span className="text-xs text-muted-foreground">({num(m.failures)})</span></TableCell>
                        <TableCell className="num text-right">{num(m.downtime_hours + m.ongoing_hours, 1, lang)} {t("unit.h")}</TableCell>
                        <TableCell className="num text-right">{kzt(Number(m.loss_kzt) + Number(m.ongoing_loss_kzt), lang)}</TableCell>
                        <TableCell className="num text-right">{m.mtbf_hours ? `${num(m.mtbf_hours, 0, lang)} ${t("unit.h")}` : "—"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
        <TopCauses report={data} pending={report.isPending} />
      </div>
    </>
  )
}
