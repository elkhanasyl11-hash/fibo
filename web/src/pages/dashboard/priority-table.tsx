import { ArrowDownIcon, ArrowUpIcon, CalendarClockIcon, ChevronDownIcon, ChevronRightIcon } from "lucide-react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { Fragment, useMemo, useState } from "react"
import { Link, useSearchParams } from "react-router"

import { getPlan } from "@/api/mocks/maintenance-plan"
import { Hint } from "@/components/hint"
import { LevelBadge } from "@/components/level"
import { MaintenanceDialog } from "@/components/maintenance-dialog"
import { Button } from "@/components/ui/button"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { useI18n, type Key } from "@/i18n"
import { featureTitle } from "@/i18n/features"
import { date, kzt, num, pct } from "@/lib/format"
import { riskLevel } from "@/lib/levels"
import { motionTokens, springs } from "@/lib/motion"
import { machineTitle, useProfiles } from "@/lib/queries"
import type { Level, Machine, RankingItem, RiskScore } from "@/lib/types"
import { cn } from "@/lib/utils"

type SortKey = "priority" | "probability" | "risk" | "name"
const MotionRow = motion.create(TableRow)
const LEVELS: Level[] = ["critical", "warning", "normal"]

// Top-3 SHAP factors (model) or weighted index signals, as signed horizontal bars.
function Factors({ score }: { score: RiskScore }) {
  const { t, lang } = useI18n()
  const reduce = useReducedMotion()
  const rows = score.shap_top3.length
    ? score.shap_top3.map((f) => ({ key: f.feature, title: featureTitle(f.feature, f.title_ru, lang), value: f.contribution, signed: true }))
    : score.signals
        .filter((s) => s.weight > 0 && s.value !== null)
        .map((s) => ({ key: s.name, title: featureTitle(s.name, s.title_ru, lang), value: (s.value ?? 0) * s.weight, signed: false }))
        .sort((a, b) => b.value - a.value)
        .slice(0, 3)
  const max = Math.max(...rows.map((r) => Math.abs(r.value)), 0.0001)
  return (
    <div className="grid gap-6 py-2 md:grid-cols-[1fr_auto]">
      <div className="flex flex-col gap-2.5">
        <span className="text-xs text-muted-foreground">{score.shap_top3.length ? t("risk.shapTop") : t("risk.signalsTop")}</span>
        {rows.length === 0 && <span className="text-sm text-muted-foreground">—</span>}
        {rows.map((row, i) => (
          <div key={row.key} className="grid grid-cols-[minmax(0,220px)_minmax(120px,1fr)_64px] items-center gap-3 text-sm">
            <span className="truncate">{row.title}</span>
            <span className="relative h-2 rounded-full bg-surface">
              <motion.span
                className={cn("absolute inset-y-0 left-0 rounded-full", row.value > 0 ? "bg-crit" : "bg-ok")}
                style={{ width: `${(Math.abs(row.value) / max) * 100}%`, originX: 0 }}
                initial={{ scaleX: reduce ? 1 : 0 }}
                animate={{ scaleX: 1 }}
                transition={{ duration: motionTokens.duration.normal, ease: motionTokens.easing.smooth, delay: i * motionTokens.stagger }}
              />
            </span>
            <span className={cn("num text-right", row.value > 0 ? "text-crit" : "text-ok")}>
              {row.signed ? (row.value > 0 ? "↑ +" : "↓ −") : ""}
              {num(Math.abs(row.value), 2, lang)}
            </span>
          </div>
        ))}
      </div>
      <p className="max-w-64 self-end text-xs text-muted-foreground text-pretty">{t("risk.shapNote")}</p>
    </div>
  )
}

export function PriorityTable({ items, machines }: { items: RankingItem[]; machines: Machine[] }) {
  const { t, lang } = useI18n()
  const profiles = useProfiles()
  const reduce = useReducedMotion()
  const [params, setParams] = useSearchParams()
  const [expanded, setExpanded] = useState<number | null>(null)
  const [planFor, setPlanFor] = useState<{ id: number; name: string } | null>(null)
  const sortKey = (params.get("sort") as SortKey) || "priority"
  const desc = params.get("dir") !== "asc"
  const level = params.get("level") as Level | null
  const type = params.get("type")
  const byId = useMemo(() => new Map(machines.map((m) => [m.id, m])), [machines])
  const types = [...new Set(items.map((i) => i.machine_type))]

  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    setParams(next, { replace: true })
  }
  const sortBy = (key: SortKey) => {
    const next = new URLSearchParams(params)
    next.set("sort", key)
    next.set("dir", sortKey === key && desc ? "asc" : "desc")
    setParams(next, { replace: true })
  }

  const rows = useMemo(() => {
    const value = (item: RankingItem): number | string =>
      sortKey === "priority"
        ? Number(item.score.priority_kzt)
        : sortKey === "risk"
          ? item.score.risk_index
          : sortKey === "probability"
            ? (item.score.failure_probability ?? -1)
            : item.machine_name.toLowerCase()
    return items
      .filter((i) => !level || riskLevel(i.score.risk_index) === level)
      .filter((i) => !type || i.machine_type === type)
      .sort((a, b) => {
        const [x, y] = [value(a), value(b)]
        const order = x < y ? -1 : x > y ? 1 : 0
        return desc ? -order : order
      })
  }, [items, sortKey, desc, level, type])

  const head = (key: SortKey, label: Key, hint?: Key, right = false) => (
    <TableHead className={cn(right && "text-right")} aria-sort={sortKey === key ? (desc ? "descending" : "ascending") : undefined}>
      <span className={cn("inline-flex items-center gap-1", right && "flex-row-reverse")}>
        <button type="button" onClick={() => sortBy(key)} className="inline-flex items-center gap-1 rounded-sm hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none">
          {t(label)}
          {sortKey === key && (desc ? <ArrowDownIcon className="size-3" /> : <ArrowUpIcon className="size-3" />)}
        </button>
        {hint && <Hint text={t(hint)} />}
      </span>
    </TableHead>
  )

  const lastMaintenance = (id: number) => {
    const machine = byId.get(id)
    const plan = getPlan(id)
    return (
      <span className="flex flex-col">
        <span className="num">{date(machine?.last_maintenance_at, lang)}</span>
        {plan && (
          <span className="flex items-center gap-1 text-xs text-primary">
            <CalendarClockIcon className="size-3" />
            {t("mnt.planned", { date: date(plan.date, lang) })}
          </span>
        )}
      </span>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <ToggleGroup type="single" size="sm" variant="outline" value={level ?? "all"} onValueChange={(v) => setParam("level", v && v !== "all" ? v : null)} aria-label={t("table.filterLevel")}>
          <ToggleGroupItem value="all" className="px-3 text-xs">{t("table.all")}</ToggleGroupItem>
          {LEVELS.map((l) => (
            <ToggleGroupItem key={l} value={l} className="px-3 text-xs">{t(`level.${l}`)}</ToggleGroupItem>
          ))}
        </ToggleGroup>
        {types.length > 1 && (
          <ToggleGroup type="single" size="sm" variant="outline" value={type ?? "all"} onValueChange={(v) => setParam("type", v && v !== "all" ? v : null)} aria-label={t("table.filterType")} className="flex-wrap">
            <ToggleGroupItem value="all" className="px-3 text-xs">{t("table.allTypes")}</ToggleGroupItem>
            {types.map((ty) => (
              <ToggleGroupItem key={ty} value={ty} className="px-3 text-xs">{machineTitle(profiles.data, ty, lang)}</ToggleGroupItem>
            ))}
          </ToggleGroup>
        )}
        <span className="num ml-auto text-xs text-muted-foreground">{t("table.shown", { n: rows.length, total: items.length })}</span>
      </div>

      <div className="hidden lg:block">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-8" />
              {head("name", "table.machine")}
              {head("probability", "table.probability", "hint.probability")}
              <TableHead>{t("table.level")}</TableHead>
              {head("priority", "table.loss", "hint.priority", true)}
              <TableHead>{t("table.lastMaintenance")}</TableHead>
              <TableHead className="text-right">{t("table.action")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((item) => {
              const open = expanded === item.machine_id
              const level = riskLevel(item.score.risk_index)
              return (
                <Fragment key={item.machine_id}>
                  <MotionRow layout={reduce ? false : "position"} transition={springs.gentle} className={cn("group h-16 cursor-pointer", level === "critical" && "bg-crit-soft/40")} onClick={() => setExpanded(open ? null : item.machine_id)}>
                    <TableCell>
                      <button type="button" aria-expanded={open} aria-label={t("table.expand")} className="flex size-8 items-center justify-center rounded-md hover:bg-muted" onClick={(e) => { e.stopPropagation(); setExpanded(open ? null : item.machine_id) }}>
                        {open ? <ChevronDownIcon className="size-4" /> : <ChevronRightIcon className="size-4 text-muted-foreground" />}
                      </button>
                    </TableCell>
                    <TableCell>
                      <Link to={`/app/machines/${item.machine_id}`} onClick={(e) => e.stopPropagation()} className="flex flex-col rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50">
                        <span className="font-medium group-hover:text-primary">{item.machine_name}</span>
                        <span className="text-xs text-muted-foreground">{machineTitle(profiles.data, item.machine_type, lang)}</span>
                      </Link>
                    </TableCell>
                    <TableCell className="w-56">
                      {item.score.failure_probability === null ? (
                        <span className="text-xs text-muted-foreground">{t("table.noModel", { index: num(item.score.risk_index, 2, lang) })}</span>
                      ) : (
                        <span className="flex items-center gap-3">
                          <span className="relative h-1.5 w-28 rounded-full bg-surface">
                            <span className="absolute inset-y-0 left-0 rounded-full bg-primary" style={{ width: `${Math.max(item.score.failure_probability * 100, 2)}%` }} />
                          </span>
                          <span className="num w-12 text-sm">{pct(item.score.failure_probability, lang)}</span>
                        </span>
                      )}
                    </TableCell>
                    <TableCell>
                      <LevelBadge level={level} />
                    </TableCell>
                    <TableCell className="num text-right font-medium">{kzt(item.score.priority_kzt, lang)}</TableCell>
                    <TableCell>{lastMaintenance(item.machine_id)}</TableCell>
                    <TableCell className="text-right">
                      <Button variant={level === "critical" ? "default" : "outline"} size="sm" onClick={(e) => { e.stopPropagation(); setPlanFor({ id: item.machine_id, name: item.machine_name }) }}>
                        {t("mnt.assign")}
                      </Button>
                    </TableCell>
                  </MotionRow>
                  <AnimatePresence initial={false}>
                    {open && (
                      <motion.tr key="details" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: motionTokens.duration.fast }} className="border-b bg-muted/30">
                        <td colSpan={7} className="px-4 pb-4 pl-14">
                          <Factors score={item.score} />
                        </td>
                      </motion.tr>
                    )}
                  </AnimatePresence>
                </Fragment>
              )
            })}
          </TableBody>
        </Table>
      </div>

      <ol className="flex flex-col gap-3 lg:hidden">
        {rows.map((item) => {
          const level = riskLevel(item.score.risk_index)
          const open = expanded === item.machine_id
          return (
            <li key={item.machine_id} className={cn("rounded-lg border bg-card p-4", level === "critical" && "shadow-glow-crit")}>
              <div className="flex items-start justify-between gap-3">
                <Link to={`/app/machines/${item.machine_id}`} className="flex min-w-0 flex-col">
                  <span className="truncate font-medium">{item.machine_name}</span>
                  <span className="text-xs text-muted-foreground">{machineTitle(profiles.data, item.machine_type, lang)}</span>
                </Link>
                <LevelBadge level={level} />
              </div>
              <dl className="mt-3 grid grid-cols-3 gap-3 text-sm">
                <div><dt className="text-xs text-muted-foreground">{t("table.probabilityShort")}</dt><dd className="num">{pct(item.score.failure_probability, lang)}</dd></div>
                <div><dt className="text-xs text-muted-foreground">{t("table.loss")}</dt><dd className="num font-medium">{kzt(item.score.priority_kzt, lang)}</dd></div>
                <div><dt className="text-xs text-muted-foreground">{t("table.lastMaintenance")}</dt><dd>{lastMaintenance(item.machine_id)}</dd></div>
              </dl>
              {open && <Factors score={item.score} />}
              <div className="mt-3 flex gap-2">
                <Button variant="ghost" size="sm" className="h-11 flex-1" aria-expanded={open} onClick={() => setExpanded(open ? null : item.machine_id)}>
                  {open ? t("table.hideFactors") : t("table.factors")}
                </Button>
                <Button variant={level === "critical" ? "default" : "outline"} size="sm" className="h-11 flex-1" onClick={() => setPlanFor({ id: item.machine_id, name: item.machine_name })}>
                  {t("mnt.assign")}
                </Button>
              </div>
            </li>
          )
        })}
      </ol>
      {planFor && <MaintenanceDialog key={planFor.id} machine={planFor} open onOpenChange={(o) => !o && setPlanFor(null)} />}
    </div>
  )
}
