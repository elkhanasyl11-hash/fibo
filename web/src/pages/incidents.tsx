import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AudioLinesIcon, BookOpenIcon, CameraIcon, CheckIcon, ChevronDownIcon, MessageSquareTextIcon, MicIcon, RotateCcwIcon } from "lucide-react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { useEffect, useRef, useState } from "react"
import { Link, useSearchParams } from "react-router"
import { toast } from "sonner"

import { AudioPlayer } from "@/components/audio-player"
import { LevelBadge } from "@/components/level"
import { PageHeader } from "@/components/page-header"
import { RichText } from "@/components/rich-text"
import { SourceBadge } from "@/components/source-badge"
import { Button } from "@/components/ui/button"
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { useI18n, type Key } from "@/i18n"
import { api } from "@/lib/api"
import { date, kzt, num } from "@/lib/format"
import { springs } from "@/lib/motion"
import { useIncidents, useMachines } from "@/lib/queries"
import { useSession } from "@/lib/session"
import type { Incident, Machine } from "@/lib/types"
import { cn } from "@/lib/utils"

const INPUT = { voice: MicIcon, audio: AudioLinesIcon, photo: CameraIcon, text: MessageSquareTextIcon }
const STATUS: Record<Incident["status"], Key> = {
  received: "inc.analyzing",
  processing: "inc.analyzing",
  open: "inc.inWork",
  resolved: "inc.fixed",
  failed: "inc.status.failed",
}
const ANALYSIS_POLL_MS = 2000

// Downtime clock for an open incident: ticks on the client from created_at, loss = hours × the
// machine's own downtime cost per hour (from the backend). Stops when the incident is resolved.
function DowntimeClock({ incident, machine }: { incident: Incident; machine: Machine | undefined }) {
  const { t, lang } = useI18n()
  const [now, setNow] = useState(() => Date.now())
  const running = incident.status === "open"
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [running])
  if (incident.status === "resolved") {
    return <span className="num text-xs text-muted-foreground">{t("inc.downtimeDone", { h: num(incident.downtime_hours ?? 0, 1, lang), kzt: kzt(incident.loss_kzt, lang) })}</span>
  }
  if (!running) return null
  const seconds = Math.max(0, (now - new Date(incident.created_at).getTime()) / 1000)
  const hh = Math.floor(seconds / 3600)
  const mm = Math.floor((seconds % 3600) / 60)
  const ss = Math.floor(seconds % 60)
  const loss = machine ? (seconds / 3600) * Number(machine.downtime_cost_per_hour_kzt) : null
  return (
    <span className="num text-xs text-crit" aria-live="off">
      {t("inc.downtimeRun")} {hh}:{String(mm).padStart(2, "0")}:{String(ss).padStart(2, "0")}
      {loss !== null && <> · {kzt(loss, lang)}</>}
    </span>
  )
}

function IncidentCard({ incident, machine, fresh }: { incident: Incident; machine: Machine | undefined; fresh: boolean }) {
  const { t, lang } = useI18n()
  const reduce = useReducedMotion()
  const client = useQueryClient()
  const [openText, setOpenText] = useState(false)
  const analyzing = incident.status === "received" || incident.status === "processing"
  const live = useQuery({
    queryKey: ["incident-live", incident.id],
    enabled: analyzing,
    refetchInterval: (q) => (q.state.data && !["received", "processing"].includes(q.state.data.status) ? false : ANALYSIS_POLL_MS),
    queryFn: () => api<Incident>(`/incidents/${incident.id}`),
  })
  useEffect(() => {
    if (live.data && !["received", "processing"].includes(live.data.status)) client.invalidateQueries({ queryKey: ["incidents"] })
  }, [live.data, client])
  const resolve = useMutation({
    mutationFn: () => api(`/incidents/${incident.id}/resolve`, { method: "PATCH" }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["incidents"] })
      toast.success(t("inc.resolvedToast"))
    },
    onError: () => toast.error(t("common.error")),
  })
  const retry = useMutation({
    mutationFn: () => api(`/incidents/${incident.id}/retry`, { method: "POST" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["incidents"] }),
    onError: () => toast.error(t("common.error")),
  })
  const Icon = INPUT[incident.input_type] ?? MicIcon
  const critical = incident.status === "open" && (incident.safety_triggered || incident.level === "critical")
  return (
    <motion.li
      layout={!reduce}
      initial={{ opacity: 0, y: reduce ? 0 : -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={springs.gentle}
      className={cn("flex flex-col gap-3 rounded-lg border bg-card p-4 shadow-card transition-colors sm:p-5", critical && "shadow-glow-crit", fresh && "ring-2 ring-primary/40")}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="flex size-9 items-center justify-center rounded-md bg-surface" aria-label={t(`input.kind.${incident.input_type}`)}>
          <Icon className="size-4 text-muted-foreground" strokeWidth={1.75} />
        </span>
        <div className="flex min-w-0 flex-col">
          <Link to={`/app/machines/${incident.machine_id}`} className="truncate font-medium hover:text-primary">{machine?.name ?? `#${incident.machine_id}`}</Link>
          <span className="num text-xs text-muted-foreground">{date(incident.created_at, lang, true)} · {t(`input.kind.${incident.input_type}`)}</span>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {analyzing ? (
            <span className="inline-flex h-6 items-center gap-1.5 rounded-full bg-surface px-2.5 text-xs"><Spinner className="size-3" />{t("inc.analyzing")}</span>
          ) : (
            <>
              <LevelBadge level={incident.level} />
              <span className="text-xs text-muted-foreground">{t(STATUS[incident.status])}</span>
            </>
          )}
        </div>
      </div>
      {incident.safety_triggered && incident.status === "open" && <p className="rounded-md bg-crit-soft px-3 py-2 text-sm font-medium text-crit">{t("safety.title")}</p>}
      {incident.safety_triggered && incident.status !== "open" && <p className="text-xs text-muted-foreground">{t("inc.safety")}</p>}
      {incident.verdict && <p className="text-[15px] text-pretty"><RichText text={incident.verdict} /></p>}
      {(incident.input_type === "voice" || incident.input_type === "audio") && <AudioPlayer incidentId={incident.id} />}
      {incident.transcript && (
        <div>
          <button type="button" onClick={() => setOpenText((o) => !o)} aria-expanded={openText} className="inline-flex h-9 items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
            <ChevronDownIcon className={cn("size-4 transition-transform", openText && "rotate-180")} />
            {t("inc.transcript")}
          </button>
          <AnimatePresence initial={false}>
            {openText && (
              <motion.p key="t" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="rounded-md bg-surface/60 px-3 py-2 text-sm text-muted-foreground">
                «{incident.transcript}»
              </motion.p>
            )}
          </AnimatePresence>
        </div>
      )}
      {incident.causes.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
          {incident.causes.map((c) => <li key={String(c)}>· {String(c)}</li>)}
        </ul>
      )}
      {incident.status === "failed" && incident.error_message && <p className="text-sm text-destructive">{incident.error_message}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <SourceBadge source={incident.ai_source} degraded={incident.degraded} />
        {incident.manual_pages.map((page) => (
          <Link key={page} to={`/app/machines/${incident.machine_id}?tab=docs&page=${page}`} className="inline-flex h-8 items-center gap-1 rounded-full border px-2.5 text-xs text-primary hover:bg-muted">
            <BookOpenIcon className="size-3" />
            {t("inc.page", { page })}
          </Link>
        ))}
        <DowntimeClock incident={incident} machine={machine} />
        <div className="ml-auto flex gap-2">
          {incident.status === "failed" && (
            <Button size="sm" variant="outline" className="h-10" onClick={() => retry.mutate()} disabled={retry.isPending}>
              {retry.isPending ? <Spinner data-icon="inline-start" /> : <RotateCcwIcon data-icon="inline-start" />}
              {t("common.retry")}
            </Button>
          )}
          {incident.status === "open" && (
            <Button size="sm" variant="outline" className="h-10" onClick={() => resolve.mutate()} disabled={resolve.isPending}>
              <CheckIcon data-icon="inline-start" />
              {t("inc.resolve")}
            </Button>
          )}
        </div>
      </div>
    </motion.li>
  )
}

export function IncidentsPage() {
  const { t } = useI18n()
  const { auth } = useSession()
  const [params, setParams] = useSearchParams()
  const status = params.get("status") ?? "all"
  const kind = params.get("kind") ?? "all"
  const incidents = useIncidents({ workshop_id: auth?.workshop.id, limit: 200 })
  const machines = useMachines(auth?.workshop.id)
  const byId = new Map((machines.data ?? []).map((m) => [m.id, m]))
  const seen = useRef<Set<number> | null>(null)
  const [fresh, setFresh] = useState<Set<number>>(new Set())

  useEffect(() => {
    if (!incidents.data) return
    const ids = incidents.data.map((i) => i.id)
    if (seen.current === null) {
      seen.current = new Set(ids)
      return
    }
    const added = ids.filter((id) => !seen.current!.has(id))
    if (added.length) {
      added.forEach((id) => seen.current!.add(id))
      setFresh(new Set(added))
      const timer = setTimeout(() => setFresh(new Set()), 4000)
      return () => clearTimeout(timer)
    }
  }, [incidents.data])

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value === "all") next.delete(key)
    else next.set(key, value)
    setParams(next, { replace: true })
  }
  const list = (incidents.data ?? [])
    .filter((i) => status === "all" || (status === "open" ? ["open", "received", "processing"].includes(i.status) : i.status === status))
    .filter((i) => kind === "all" || i.input_type === kind)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))

  return (
    <>
      <PageHeader title={t("incp.title")} description={t("incp.lead")} />
      <div className="flex flex-wrap items-center gap-2">
        <ToggleGroup type="single" size="sm" variant="outline" value={status} onValueChange={(v) => v && set("status", v)} aria-label={t("incp.byStatus")}>
          {(["all", "open", "resolved", "failed"] as const).map((s) => (
            <ToggleGroupItem key={s} value={s} className="h-10 px-3 text-xs">{t(`incp.s.${s}`)}</ToggleGroupItem>
          ))}
        </ToggleGroup>
        <ToggleGroup type="single" size="sm" variant="outline" value={kind} onValueChange={(v) => v && set("kind", v)} aria-label={t("incp.byKind")}>
          <ToggleGroupItem value="all" className="h-10 px-3 text-xs">{t("table.all")}</ToggleGroupItem>
          {(["voice", "audio", "photo", "text"] as const).map((k) => {
            const Icon = INPUT[k]
            return (
              <ToggleGroupItem key={k} value={k} className="h-10 px-3 text-xs" aria-label={t(`input.kind.${k}`)}>
                <Icon className="size-4" />
                <span className="hidden sm:inline">{t(`input.kind.${k}`)}</span>
              </ToggleGroupItem>
            )
          })}
        </ToggleGroup>
        <span className="num ml-auto text-xs text-muted-foreground">{t("table.shown", { n: list.length, total: incidents.data?.length ?? 0 })}</span>
      </div>
      {incidents.isPending ? (
        <div className="flex flex-col gap-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-36 w-full" />)}</div>
      ) : list.length === 0 ? (
        <Empty className="border bg-card shadow-card">
          <EmptyHeader>
            <EmptyTitle>{t("inc.emptyTitle")}</EmptyTitle>
            <EmptyDescription>{t("feed.empty")}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <ul className="flex flex-col gap-3">
          <AnimatePresence initial={false}>
            {list.slice(0, 100).map((incident) => (
              <IncidentCard key={incident.id} incident={incident} machine={byId.get(incident.machine_id)} fresh={fresh.has(incident.id)} />
            ))}
          </AnimatePresence>
        </ul>
      )}
    </>
  )
}
