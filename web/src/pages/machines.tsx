import { useMemo, useState } from "react"
import {
  ArrowRightIcon,
  CalendarClockIcon,
  LayoutGridIcon,
  ListIcon,
  PlusIcon,
  SearchIcon,
} from "lucide-react"
import { Link, useSearchParams } from "react-router"
import { LevelBadge } from "@/components/level"
import { PageHeader } from "@/components/page-header"
import { RiskBar } from "@/components/risk-bar"
import { Button } from "@/components/ui/button"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { useI18n } from "@/i18n"
import { date, kzt, num } from "@/lib/format"
import { RISK_WARN, riskLevel } from "@/lib/levels"
import {
  machineTitle,
  useMachines,
  useProfiles,
  useRanking,
} from "@/lib/queries"
import { useSession } from "@/lib/session"
import type { Machine } from "@/lib/types"

export function hoursUntilMaintenance(machine: Machine, now = Date.now()) {
  return machine.last_maintenance_at && machine.maintenance_interval_hours
    ? machine.maintenance_interval_hours -
        (now - new Date(machine.last_maintenance_at).getTime()) / 3_600_000
    : null
}

export function MachinesPage() {
  const { t, lang } = useI18n()
  const kk = lang === "kk"
  const { auth } = useSession()
  const machines = useMachines(auth?.workshop.id)
  const ranking = useRanking(auth?.workshop.id)
  const profiles = useProfiles()
  const [search, setSearch] = useState("")
  const [view, setView] = useState<"grid" | "list">("grid")
  const [sort, setSort] = useState("priority")
  const [params, setParams] = useSearchParams()
  const filter = params.get("state") ?? "all"
  const scores = useMemo(
    () =>
      new Map(
        (ranking.data?.items ?? []).map((row) => [row.machine_id, row.score])
      ),
    [ranking.data]
  )
  const rows = (machines.data ?? [])
    .filter((machine) => {
      const score = scores.get(machine.id)
      const match =
        `${machine.name} ${machine.model ?? ""} ${machineTitle(profiles.data, machine.type, lang)}`
          .toLowerCase()
          .includes(search.toLowerCase())
      return (
        match &&
        (filter === "all" ||
          (filter === "attention" && score && score.risk_index >= RISK_WARN) ||
          (filter === "unknown" && !score) ||
          (filter === "overdue" &&
            (hoursUntilMaintenance(machine) ?? Infinity) < 0))
      )
    })
    .sort((a, b) =>
      sort === "name"
        ? a.name.localeCompare(b.name, lang)
        : sort === "maintenance"
          ? (hoursUntilMaintenance(a) ?? Infinity) -
            (hoursUntilMaintenance(b) ?? Infinity)
          : Number(scores.get(b.id)?.priority_kzt ?? -1) -
            Number(scores.get(a.id)?.priority_kzt ?? -1)
    )
  const count = machines.data?.length ?? 0
  const attention = (machines.data ?? []).filter(
    (machine) => (scores.get(machine.id)?.risk_index ?? 0) >= RISK_WARN
  ).length
  const overdue = (machines.data ?? []).filter(
    (machine) => (hoursUntilMaintenance(machine) ?? Infinity) < 0
  ).length
  const unknown = (machines.data ?? []).filter(
    (machine) => !scores.has(machine.id)
  ).length
  const filters = [
    { id: "all", label: kk ? "Барлығы" : "Всё оборудование", count },
    {
      id: "attention",
      label: kk ? "Назар аудару" : "Требуют внимания",
      count: attention,
    },
    {
      id: "overdue",
      label: kk ? "ТҚ мерзімі өтті" : "ТО просрочено",
      count: overdue,
    },
    {
      id: "unknown",
      label: kk ? "Бағаланбаған" : "Без оценки",
      count: unknown,
    },
  ]
  return (
    <>
      <PageHeader
        title={t("machines.title")}
        description={
          kk
            ? "Жабдықтар, тәуекел және техникалық қызмет мерзімі"
            : "Оборудование, риски и сроки обслуживания"
        }
        actions={
          <Button asChild>
            <Link to="/app/machines/new">
              <PlusIcon />
              {t("machines.add")}
            </Link>
          </Button>
        }
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {filters.map((item) => (
          <button
            type="button"
            key={item.id}
            aria-pressed={filter === item.id}
            onClick={() =>
              setParams(item.id === "all" ? {} : { state: item.id }, {
                replace: true,
              })
            }
            className={`flex flex-col gap-4 rounded-xl border p-4 text-left transition-colors ${filter === item.id ? "border-primary/50 bg-primary/5" : "bg-card hover:bg-muted"}`}
          >
            <span className="text-xs text-muted-foreground">{item.label}</span>
            <strong
              className={`num text-3xl font-medium ${item.id === "overdue" && item.count ? "text-crit" : ""}`}
            >
              {machines.isPending ? "…" : item.count}
            </strong>
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-48 flex-1">
          <SearchIcon className="pointer-events-none absolute top-3 left-3 size-4 text-muted-foreground" />
          <Input
            aria-label={kk ? "Жабдық іздеу" : "Поиск оборудования"}
            placeholder={
              kk ? "Атауы немесе моделі" : "Название или модель станка"
            }
            className="h-10 rounded-md pl-10"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          aria-label={kk ? "Сұрыптау" : "Сортировка оборудования"}
          value={sort}
          onChange={(e) => setSort(e.target.value)}
          className="h-10 rounded-md border bg-card px-3 text-sm"
        >
          <option value="priority">
            {kk ? "Басымдық бойынша" : "По приоритету"}
          </option>
          <option value="name">{kk ? "Атауы бойынша" : "По названию"}</option>
          <option value="maintenance">
            {kk ? "ТҚ мерзімі бойынша" : "По сроку ТО"}
          </option>
        </select>
        <div
          role="group"
          aria-label={kk ? "Көрініс" : "Вид списка"}
          className="flex gap-1"
        >
          <Button
            variant={view === "grid" ? "secondary" : "ghost"}
            size="icon"
            aria-label={kk ? "Карточкалар" : "Карточки"}
            aria-pressed={view === "grid"}
            onClick={() => setView("grid")}
          >
            <LayoutGridIcon />
          </Button>
          <Button
            variant={view === "list" ? "secondary" : "ghost"}
            size="icon"
            aria-label={kk ? "Тізім" : "Список"}
            aria-pressed={view === "list"}
            onClick={() => setView("list")}
          >
            <ListIcon />
          </Button>
        </div>
      </div>
      {machines.isPending ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      ) : machines.isError ? (
        <Empty className="border">
          <EmptyHeader>
            <EmptyTitle>
              {kk ? "Жүктеу қатесі" : "Не удалось загрузить оборудование"}
            </EmptyTitle>
          </EmptyHeader>
          <Button variant="outline" onClick={() => machines.refetch()}>
            {t("common.retry")}
          </Button>
        </Empty>
      ) : !count ? (
        <Empty className="border bg-card py-12">
          <EmptyHeader>
            <EmptyTitle>{t("dash.emptyTitle")}</EmptyTitle>
            <EmptyDescription>{t("dash.empty")}</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button asChild>
              <Link to="/app/machines/new">{t("machines.addFirst")}</Link>
            </Button>
          </EmptyContent>
        </Empty>
      ) : !rows.length ? (
        <Empty className="border bg-card">
          <EmptyHeader>
            <EmptyTitle>
              {kk ? "Сәйкес жабдық табылмады" : "Оборудование не найдено"}
            </EmptyTitle>
            <EmptyDescription>
              {kk
                ? "Іздеуді немесе сүзгіні өзгертіңіз"
                : "Измените запрос или сбросьте фильтр"}
            </EmptyDescription>
          </EmptyHeader>
          <Button
            variant="outline"
            onClick={() => {
              setSearch("")
              setParams({}, { replace: true })
            }}
          >
            {kk ? "Сүзгілерді тазалау" : "Сбросить фильтры"}
          </Button>
        </Empty>
      ) : (
        <ul
          className={
            view === "grid"
              ? "grid gap-4 md:grid-cols-2 xl:grid-cols-3"
              : "flex flex-col gap-3"
          }
        >
          {rows.map((machine) => {
            const score = scores.get(machine.id)
            const remaining = hoursUntilMaintenance(machine)
            return (
              <li key={machine.id}>
                <Link
                  to={`/app/machines/${machine.id}`}
                  className={`group flex h-full flex-col overflow-hidden rounded-xl border bg-card transition-colors outline-none hover:border-primary/40 focus-visible:ring-2 focus-visible:ring-primary ${view === "list" ? "lg:flex-row lg:items-center" : ""}`}
                >
                  <div
                    className={`flex flex-1 flex-col gap-4 p-5 ${view === "list" ? "lg:flex-row lg:items-center lg:gap-8" : ""}`}
                  >
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <span className="text-xs text-muted-foreground">
                        {machineTitle(profiles.data, machine.type, lang)}
                      </span>
                      <h2 className="truncate text-xl font-medium">
                        {machine.name}
                      </h2>
                      <span className="truncate text-xs text-muted-foreground">
                        {machine.model ||
                          (kk ? "Моделі көрсетілмеген" : "Модель не указана")}
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-4">
                      <LevelBadge level={riskLevel(score?.risk_index)} />
                      <span className="num text-sm text-muted-foreground">
                        {score ? num(score.risk_index, 2, lang) : "—"}
                      </span>
                    </div>
                    {view === "grid" && (
                      <RiskBar
                        value={score?.risk_index ?? null}
                        showValue={false}
                      />
                    )}
                    <dl
                      className={`grid gap-4 text-xs ${view === "grid" ? "grid-cols-2" : "grid-cols-2 lg:min-w-80"}`}
                    >
                      <div>
                        <dt className="mb-1 text-muted-foreground">
                          {kk ? "Соңғы ТҚ" : "Последнее ТО"}
                        </dt>
                        <dd>
                          {machine.last_maintenance_at
                            ? date(machine.last_maintenance_at, lang)
                            : kk
                              ? "Тіркелмеген"
                              : "Не записано"}
                        </dd>
                      </div>
                      <div>
                        <dt className="mb-1 text-muted-foreground">
                          {t("table.priority")}
                        </dt>
                        <dd className="num">
                          {score ? kzt(score.priority_kzt, lang) : "—"}
                        </dd>
                      </div>
                    </dl>
                  </div>
                  <div
                    className={`flex items-center justify-between gap-3 border-t bg-muted/30 px-5 py-3 text-xs ${view === "list" ? "lg:w-52 lg:self-stretch lg:border-t-0 lg:border-l" : ""}`}
                  >
                    <span
                      className={`flex items-center gap-2 ${remaining !== null && remaining < 0 ? "text-crit" : "text-muted-foreground"}`}
                    >
                      <CalendarClockIcon className="size-4" />
                      {remaining === null
                        ? kk
                          ? "ТҚ кестесі жоқ"
                          : "График ТО не задан"
                        : remaining < 0
                          ? kk
                            ? `Кешікті: ${Math.ceil(-remaining / 24)} күн`
                            : `Просрочено на ${Math.ceil(-remaining / 24)} дн.`
                          : kk
                            ? `ТҚ дейін ${Math.ceil(remaining / 24)} күн`
                            : `До ТО ${Math.ceil(remaining / 24)} дн.`}
                    </span>
                    <ArrowRightIcon className="size-4 text-muted-foreground transition-colors group-hover:text-primary" />
                  </div>
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </>
  )
}
