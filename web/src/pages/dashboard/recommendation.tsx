import { useQuery } from "@tanstack/react-query"
import { ArrowRightIcon, CheckIcon, ChevronLeftIcon, ChevronRightIcon } from "lucide-react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { useState } from "react"
import { Link } from "react-router"

import { AnimatedNumber } from "@/components/animated-number"
import { RiskBar } from "@/components/risk-bar"
import { SourceBadge } from "@/components/source-badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Spinner } from "@/components/ui/spinner"
import { Trace, TraceIcon, TraceLine, TraceTitle } from "@/components/ui/trace"
import { useI18n, type Key } from "@/i18n"
import { api } from "@/lib/api"
import { kzt } from "@/lib/format"
import { motionTokens, springs } from "@/lib/motion"
import type { AdviceOption, AdviceResponse, RankingItem } from "@/lib/types"

const CATEGORY: Record<AdviceOption["category"], Key> = {
  maintenance: "advice.cat.maintenance",
  quality: "advice.cat.quality",
  process: "advice.cat.process",
  data: "advice.cat.data",
}

function Thinking({ machine }: { machine: string }) {
  const { t } = useI18n()
  const reduce = useReducedMotion()
  const lines = [t("rec.step1", { machine }), t("rec.step2"), t("rec.step3")]
  return (
    <Trace>
      {lines.map((line, i) => (
        <motion.div
          key={line}
          initial={{ opacity: 0, y: reduce ? 0 : motionTokens.distance.xs }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...springs.gentle, delay: i * 0.5 }}
        >
          <TraceLine status={i === lines.length - 1 ? "running" : undefined}>
            <TraceIcon>{i === lines.length - 1 ? <Spinner /> : <CheckIcon />}</TraceIcon>
            <TraceTitle>{line}</TraceTitle>
          </TraceLine>
        </motion.div>
      ))}
    </Trace>
  )
}

// "Fibo recommends": the first machine of the repair queue and what to do with it. The options and
// their wording come from /ai/advice (AI or built-in); every tenge figure is the backend's what-if.
export function Recommendation({ top }: { top: RankingItem | undefined }) {
  const { t, lang } = useI18n()
  const reduce = useReducedMotion()
  const [index, setIndex] = useState(0)
  const [direction, setDirection] = useState(1)
  const advice = useQuery({
    queryKey: ["advice", top?.machine_id, lang],
    enabled: top !== undefined,
    staleTime: 10 * 60_000,
    queryFn: () => api<AdviceResponse>("/ai/advice", { method: "POST", json: { machine_id: top!.machine_id, language: lang } }),
  })
  const options = [...(advice.data?.options ?? [])].sort((a, b) => Number(b.saves_kzt ?? -1) - Number(a.saves_kzt ?? -1))
  const option = options[Math.min(index, options.length - 1)]
  const go = (step: number) => {
    setDirection(step)
    setIndex((i) => (i + step + options.length) % options.length)
  }

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle className="text-base font-medium">{t("rec.title")}</CardTitle>
        <CardDescription>{top ? t("rec.lead", { machine: top.machine_name }) : t("rec.none")}</CardDescription>
      </CardHeader>
      <CardContent className="flex min-h-56 flex-1 flex-col">
        {!top ? null : advice.isPending ? (
          <Thinking machine={top.machine_name} />
        ) : advice.isError || !option ? (
          <p className="text-sm text-muted-foreground">{t("advice.failed")}</p>
        ) : (
          <AnimatePresence mode="wait" custom={direction} initial={false}>
            <motion.div
              key={option.id}
              className="flex flex-col gap-4"
              initial={{ opacity: 0, x: reduce ? 0 : direction * motionTokens.distance.md }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: reduce ? 0 : -direction * motionTokens.distance.md }}
              transition={{ duration: motionTokens.duration.fast, ease: motionTokens.easing.smooth }}
            >
              <span className="text-xs text-muted-foreground">{t(CATEGORY[option.category])}</span>
              <div className="flex flex-col gap-1.5">
                <h3 className="text-[17px] font-medium text-pretty">{option.title}</h3>
                <p className="text-sm text-muted-foreground text-pretty">{option.why}</p>
              </div>
              {option.saves_kzt !== null && Number(option.saves_kzt) > 0 && (
                <div className="flex flex-col gap-3 rounded-lg bg-surface p-3">
                  <div className="flex flex-col gap-1">
                    <span className="text-xs text-muted-foreground">{t("rec.saves")}</span>
                    <span className="display text-[26px] leading-none whitespace-nowrap text-ok">
                      −<AnimatedNumber value={Number(option.saves_kzt)} format={(v) => kzt(v, lang)} />
                    </span>
                  </div>
                  {option.risk_before !== null && option.risk_after !== null && (
                    <div className="grid grid-cols-2 gap-3 text-xs text-muted-foreground">
                      <div className="flex flex-col gap-1">
                        {t("whatif.nowLabel")}
                        <RiskBar value={option.risk_before} />
                      </div>
                      <div className="flex flex-col gap-1">
                        {t("whatif.afterLabel")}
                        <RiskBar value={option.risk_after} />
                      </div>
                    </div>
                  )}
                </div>
              )}
            </motion.div>
          </AnimatePresence>
        )}
      </CardContent>
      {top && (
        <CardFooter className="justify-between gap-2">
          <div className="flex items-center gap-1">
            {options.length > 1 && (
              <>
                <Button variant="ghost" size="icon-sm" aria-label={t("rec.prev")} onClick={() => go(-1)}>
                  <ChevronLeftIcon />
                </Button>
                <span className="num w-10 text-center text-xs text-muted-foreground">
                  {Math.min(index, options.length - 1) + 1}/{options.length}
                </span>
                <Button variant="ghost" size="icon-sm" aria-label={t("rec.next")} onClick={() => go(1)}>
                  <ChevronRightIcon />
                </Button>
              </>
            )}
            {advice.data && <SourceBadge source={advice.data.source} className="ml-1" />}
          </div>
          <Button asChild size="sm" variant="outline">
            <Link to={`/app/machines/${top.machine_id}`}>
              {t("rec.open")}
              <ArrowRightIcon data-icon="inline-end" />
            </Link>
          </Button>
        </CardFooter>
      )}
    </Card>
  )
}
