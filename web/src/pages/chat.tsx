import { useMutation, useQuery } from "@tanstack/react-query"
import {
  ActivityIcon,
  ArrowUpIcon,
  BanknoteIcon,
  CheckIcon,
  ListOrderedIcon,
  RotateCcwIcon,
  WrenchIcon,
} from "lucide-react"
import { motion, useReducedMotion } from "motion/react"
import { useState } from "react"
import { Link } from "react-router"

import { BrandMark } from "@/components/brand"
import { PageHeader } from "@/components/page-header"
import { RichText } from "@/components/rich-text"
import { RiskBar } from "@/components/risk-bar"
import { Bubble, BubbleContent } from "@/components/ui/bubble"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardFooter } from "@/components/ui/card"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from "@/components/ui/input-group"
import { Marker, MarkerContent, MarkerIcon } from "@/components/ui/marker"
import { Message, MessageAvatar, MessageContent } from "@/components/ui/message"
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller"
import { Spinner } from "@/components/ui/spinner"
import { Trace, TraceIcon, TraceLine, TraceTitle } from "@/components/ui/trace"
import { useI18n, type Key } from "@/i18n"
import { api, ApiError } from "@/lib/api"
import { kzt } from "@/lib/format"
import { motionTokens, springs } from "@/lib/motion"
import { useIncidents, useRanking } from "@/lib/queries"
import { useSession } from "@/lib/session"
import type { AssistantResponse, ChatTurn, RankingItem } from "@/lib/types"

const TOOL: Record<string, Key> = {
  get_risk_ranking: "chat.tool.ranking",
  get_machine_summary: "chat.tool.machine",
  get_incidents: "chat.tool.incidents",
  get_downtime_report: "chat.tool.report",
  get_reading_trends: "chat.tool.trends",
  get_maintenance_plan: "chat.tool.plan",
  compare_maintenance: "chat.tool.scenario",
}

interface Entry {
  id: string
  turn: ChatTurn
  reply?: AssistantResponse
  failed?: boolean
  error?: unknown
}

function MiniTable({ ids, items }: { ids: number[]; items: RankingItem[] }) {
  const { t, lang } = useI18n()
  const rows = ids
    .map((id) => items.find((i) => i.machine_id === id))
    .filter((r): r is RankingItem => Boolean(r))
  if (rows.length === 0) return null
  return (
    <div className="w-full max-w-md overflow-hidden rounded-lg border bg-card">
      <div className="grid grid-cols-[minmax(0,1fr)_128px_96px] gap-4 border-b px-3 py-2 text-xs text-muted-foreground">
        <span>{t("table.machine")}</span>
        <span>{t("table.risk")}</span>
        <span className="text-right">{t("table.priority")}</span>
      </div>
      {rows.map((row) => (
        <Link
          key={row.machine_id}
          to={`/app/machines/${row.machine_id}`}
          className="grid grid-cols-[minmax(0,1fr)_128px_96px] items-center gap-4 px-3 py-2.5 text-sm transition-colors not-last:border-b hover:bg-muted"
        >
          <span className="truncate font-medium">{row.machine_name}</span>
          <RiskBar value={row.score.risk_index} />
          <span className="num text-right">
            {kzt(row.score.priority_kzt, lang)}
          </span>
        </Link>
      ))}
    </div>
  )
}

function ToolSteps({ tools }: { tools: string[] }) {
  const { t } = useI18n()
  const reduce = useReducedMotion()
  if (tools.length === 0) return null
  return (
    <Trace>
      {tools.map((tool, i) => (
        <motion.div
          key={`${tool}-${i}`}
          initial={{ opacity: 0, y: reduce ? 0 : motionTokens.distance.xs }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            ...springs.gentle,
            delay: i * motionTokens.stagger * 2,
          }}
        >
          <TraceLine>
            <TraceIcon>
              <CheckIcon />
            </TraceIcon>
            <TraceTitle>{TOOL[tool] ? t(TOOL[tool]) : tool}</TraceTitle>
          </TraceLine>
        </motion.div>
      ))}
    </Trace>
  )
}

function Answer({ text }: { text: string }) {
  const reduce = useReducedMotion()
  const paragraphs = text.split(/\n{2,}/).filter((p) => p.trim())
  return (
    <>
      {paragraphs.map((paragraph, i) => (
        <motion.p
          key={i}
          className="whitespace-pre-wrap not-last:mb-3"
          initial={{ opacity: 0, y: reduce ? 0 : motionTokens.distance.xs }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: motionTokens.duration.normal,
            ease: motionTokens.easing.smooth,
            delay: 0.15 + i * 0.08,
          }}
        >
          <RichText text={paragraph} />
        </motion.p>
      ))}
    </>
  )
}

function FollowUps({
  ids,
  items,
  asked,
  onAsk,
}: {
  ids: number[]
  items: RankingItem[]
  asked: string
  onAsk: (q: string) => void
}) {
  const { t } = useI18n()
  const names = ids
    .map((id) => items.find((i) => i.machine_id === id)?.machine_name)
    .filter((n): n is string => Boolean(n))
  const questions = names
    .slice(0, 2)
    .flatMap((name) => [
      t("chat.f1", { machine: name }),
      t("chat.f2", { machine: name }),
    ])
    .filter((q) => q.trim().toLowerCase() !== asked.trim().toLowerCase())
    .slice(0, 3)
  if (questions.length === 0) return null
  return (
    <div className="flex flex-wrap gap-2">
      {questions.map((q) => (
        <button
          key={q}
          type="button"
          onClick={() => onAsk(q)}
          className="rounded-full border bg-card px-3 py-1.5 text-left text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          {q}
        </button>
      ))}
    </div>
  )
}

export function ChatPage() {
  const { t, lang } = useI18n()
  const { auth } = useSession()
  const ranking = useRanking(auth?.workshop.id)
  const openIncidents = useIncidents({
    workshop_id: auth?.workshop.id,
    status: "open",
    limit: 100,
  })
  const [entries, setEntries] = useState<Entry[]>([])
  const [draft, setDraft] = useState("")
  const [mode, setMode] = useState<"live" | "offline">("live")
  const connection = useQuery({
    queryKey: ["assistant-status"],
    queryFn: () =>
      api<{ configured: boolean; model: string | null }>(
        "/ai/assistant/status"
      ),
    staleTime: 30_000,
  })
  const ask = useMutation({
    mutationFn: (history: ChatTurn[]) =>
      api<AssistantResponse>("/ai/assistant/chat", {
        method: "POST",
        timeoutMs: 75_000,
        json: {
          workshop_id: auth?.workshop.id,
          mode,
          messages: history.slice(-20),
          language: lang,
        },
      }),
  })
  const send = (text: string, retryId?: string) => {
    const content = text.trim().slice(0, 4000)
    if (!content || ask.isPending) return
    const history: ChatTurn[] = [
      ...entries.flatMap((e) =>
        e.reply
          ? [
              e.turn,
              {
                role: "assistant" as const,
                content: e.reply.answer.slice(0, 4000),
              },
            ]
          : e.failed
            ? []
            : [e.turn]
      ),
      { role: "user", content },
    ]
    const id = retryId ?? crypto.randomUUID()
    setEntries((list) =>
      retryId
        ? list.map((entry) =>
            entry.id === id ? { id, turn: entry.turn } : entry
          )
        : [...list, { id, turn: { role: "user", content } }]
    )
    setDraft("")
    ask.mutate(history, {
      onSuccess: (reply) =>
        setEntries((list) =>
          list.map((e) => (e.id === id ? { ...e, reply } : e))
        ),
      onError: (error) =>
        setEntries((list) =>
          list.map((e) => (e.id === id ? { ...e, failed: true, error } : e))
        ),
    })
  }
  const items = ranking.data?.items ?? []
  const suggestions = [
    { icon: ListOrderedIcon, title: t("chat.s1"), q: t("chat.q1") },
    { icon: BanknoteIcon, title: t("chat.s2"), q: t("chat.q2") },
    items[0]
      ? {
          icon: ActivityIcon,
          title: t("chat.s3"),
          q: t("chat.q3", { machine: items[0].machine_name }),
        }
      : { icon: ActivityIcon, title: t("chat.s3"), q: t("chat.q4") },
    {
      icon: WrenchIcon,
      title: t("chat.s4"),
      q:
        lang === "kk"
          ? "ТҚ жоспары қандай?"
          : "Составь план обслуживания оборудования",
    },
  ]
  const errorText = (error: unknown) => {
    if (!(error instanceof ApiError)) return t("chat.failed")
    if (error.code === "timeout" || error.details.reason === "timeout")
      return t("chat.timeout")
    if (error.status === 0) return t("common.offline")
    if (error.details.reason === "not_configured")
      return t("chat.notConfigured")
    if (error.details.reason === "authentication") return t("chat.apiAuth")
    if (error.details.reason === "provider_configuration")
      return t("chat.apiConfig")
    if (error.status === 429 || error.details.reason === "rate_limited")
      return t("chat.throttled")
    return t("chat.apiUnavailable")
  }

  return (
    <>
      <PageHeader
        title={t("chat.title")}
        description={t("chat.lead")}
        meta={
          <span>
            {t("chat.context", {
              machines: items.length,
              open: openIncidents.data?.length ?? 0,
            })}
          </span>
        }
        actions={
          entries.length > 0 && (
            <Button
              variant="outline"
              onClick={() => setEntries([])}
              disabled={ask.isPending}
            >
              <RotateCcwIcon data-icon="inline-start" />
              {t("chat.reset")}
            </Button>
          )
        }
      />
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <span role="status">
          {mode === "offline"
            ? t("chat.offlineMode")
            : connection.isPending
              ? t("chat.checking")
              : connection.isError
                ? t("chat.statusFailed")
                : connection.data?.configured
                  ? `AI · ${connection.data.model}`
                  : t("chat.notConfigured")}
        </span>
        <div className="flex gap-2">
          {(connection.isError || !connection.data?.configured) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => connection.refetch()}
              disabled={connection.isFetching}
            >
              {t("chat.recheck")}
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            disabled={ask.isPending}
            onClick={() => {
              setMode(mode === "live" ? "offline" : "live")
              setEntries([])
            }}
          >
            {mode === "live" ? t("chat.useOffline") : t("chat.useAI")}
          </Button>
        </div>
      </div>
      <Card className="h-[calc(100svh-18rem)] min-h-[480px] gap-0 py-0">
        <CardContent className="min-h-0 flex-1 overflow-hidden p-0">
          <MessageScrollerProvider>
            <MessageScroller>
              <MessageScrollerViewport>
                <MessageScrollerContent className="p-4 sm:p-6">
                  {entries.length === 0 && (
                    <MessageScrollerItem>
                      <div className="mx-auto flex w-full max-w-2xl flex-col gap-5 py-6 sm:py-10">
                        <div className="flex flex-col gap-1.5">
                          <h2 className="display text-2xl">
                            {t("chat.hello")}
                          </h2>
                          <p className="text-sm text-pretty text-muted-foreground">
                            {t("chat.helloLead")}
                          </p>
                        </div>
                        <div className="grid gap-3 sm:grid-cols-2">
                          {suggestions.map(({ icon: Icon, title, q }, i) => (
                            <motion.button
                              key={q}
                              type="button"
                              onClick={() => send(q)}
                              disabled={ask.isPending}
                              initial={{
                                opacity: 0,
                                y: motionTokens.distance.sm,
                              }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={{
                                duration: motionTokens.duration.normal,
                                ease: motionTokens.easing.smooth,
                                delay: i * 0.05,
                              }}
                              className="flex flex-col items-start gap-2 rounded-lg border bg-card p-4 text-left shadow-card transition-colors outline-none hover:border-foreground/20 focus-visible:ring-3 focus-visible:ring-ring/40"
                            >
                              <span className="flex items-center gap-2 text-xs text-muted-foreground">
                                <Icon className="size-4" strokeWidth={1.75} />
                                {title}
                              </span>
                              <span className="text-sm text-pretty">{q}</span>
                            </motion.button>
                          ))}
                        </div>
                      </div>
                    </MessageScrollerItem>
                  )}
                  {entries.map((entry) => (
                    <div key={entry.id} className="contents">
                      <MessageScrollerItem
                        messageId={`${entry.id}-q`}
                        scrollAnchor
                      >
                        <Message align="end">
                          <MessageContent>
                            <Bubble variant="default">
                              <BubbleContent className="whitespace-pre-wrap">
                                {entry.turn.content}
                              </BubbleContent>
                            </Bubble>
                          </MessageContent>
                        </Message>
                      </MessageScrollerItem>
                      <MessageScrollerItem messageId={`${entry.id}-a`}>
                        <Message align="start">
                          <MessageAvatar>
                            <BrandMark className="size-7" />
                          </MessageAvatar>
                          <MessageContent>
                            {!entry.reply && !entry.failed && (
                              <Marker role="status">
                                <MarkerIcon>
                                  <Spinner />
                                </MarkerIcon>
                                <MarkerContent>
                                  {t("chat.thinking")}
                                </MarkerContent>
                              </Marker>
                            )}
                            {entry.failed && (
                              <Bubble variant="destructive">
                                <BubbleContent>
                                  {errorText(entry.error)}
                                  {entry === entries.at(-1) && (
                                    <Button
                                      className="mt-3"
                                      size="sm"
                                      variant="outline"
                                      disabled={ask.isPending}
                                      onClick={() =>
                                        send(entry.turn.content, entry.id)
                                      }
                                    >
                                      <RotateCcwIcon data-icon="inline-start" />
                                      {t("chat.retry")}
                                    </Button>
                                  )}
                                </BubbleContent>
                              </Bubble>
                            )}
                            {entry.reply && (
                              <>
                                <span className="text-xs text-muted-foreground">
                                  {entry.reply.source === "ai"
                                    ? lang === "kk"
                                      ? "AI талдауы"
                                      : "AI-анализ"
                                    : lang === "kk"
                                      ? "Деректер бойынша есеп · ережелер режимі"
                                      : "Расчёт по данным · режим правил"}
                                  {entry.reply.degraded?.length
                                    ? lang === "kk"
                                      ? " · AI қолжетімсіз"
                                      : " · AI недоступен"
                                    : ""}
                                </span>
                                <ToolSteps tools={entry.reply.tools_used} />
                                <Bubble variant="muted">
                                  <BubbleContent>
                                    <Answer text={entry.reply.answer} />
                                  </BubbleContent>
                                </Bubble>
                                <MiniTable
                                  ids={entry.reply.referenced_machine_ids}
                                  items={items}
                                />
                                {entry === entries.at(-1) && (
                                  <FollowUps
                                    ids={entry.reply.referenced_machine_ids}
                                    items={items}
                                    asked={entry.turn.content}
                                    onAsk={send}
                                  />
                                )}
                              </>
                            )}
                          </MessageContent>
                        </Message>
                      </MessageScrollerItem>
                    </div>
                  ))}
                </MessageScrollerContent>
              </MessageScrollerViewport>
              <MessageScrollerButton />
            </MessageScroller>
          </MessageScrollerProvider>
        </CardContent>
        <CardFooter className="border-t bg-card p-3 sm:p-4">
          <form
            className="w-full"
            onSubmit={(e) => {
              e.preventDefault()
              send(draft)
            }}
          >
            <InputGroup className="h-auto">
              <InputGroupTextarea
                aria-label={t("chat.placeholder")}
                placeholder={t("chat.placeholder")}
                maxLength={4000}
                className="min-h-11 py-3"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (
                    e.key === "Enter" &&
                    !e.shiftKey &&
                    !e.nativeEvent.isComposing
                  ) {
                    e.preventDefault()
                    send(draft)
                  }
                }}
              />
              <InputGroupAddon align="inline-end" className="self-end pb-1.5">
                <InputGroupButton
                  type="submit"
                  variant="default"
                  size="icon-sm"
                  disabled={!draft.trim() || ask.isPending}
                  aria-label={t("chat.send")}
                >
                  <ArrowUpIcon />
                </InputGroupButton>
              </InputGroupAddon>
            </InputGroup>
          </form>
        </CardFooter>
      </Card>
    </>
  )
}
