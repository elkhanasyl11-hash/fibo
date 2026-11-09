import { useQuery } from "@tanstack/react-query"
import { CheckIcon, RefreshCwIcon } from "lucide-react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"

import { RiskBar } from "@/components/risk-bar"
import { SourceBadge } from "@/components/source-badge"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Spinner } from "@/components/ui/spinner"
import { Trace, TraceIcon, TraceLine, TraceTitle } from "@/components/ui/trace"
import { useIsMobile } from "@/hooks/use-mobile"
import { useI18n, type Key } from "@/i18n"
import { api } from "@/lib/api"
import { kzt } from "@/lib/format"
import { motionTokens, springs } from "@/lib/motion"
import type { AdviceOption, AdviceResponse, Machine } from "@/lib/types"
import type { Scenario } from "./what-if"

const CATEGORY: Record<AdviceOption["category"], Key> = {
  maintenance: "advice.cat.maintenance",
  quality: "advice.cat.quality",
  process: "advice.cat.process",
  data: "advice.cat.data",
}

function Working({ toolApplies }: { toolApplies: boolean }) {
  const { t } = useI18n()
  const reduce = useReducedMotion()
  const lines: Key[] = ["advice.step.maintenance", ...(toolApplies ? (["advice.step.tool"] as Key[]) : []), "advice.step.ai"]
  return (
    <Trace>
      {lines.map((line, i) => (
        <motion.div
          key={line}
          initial={{ opacity: 0, y: reduce ? 0 : motionTokens.distance.xs }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...springs.gentle, delay: i * 0.4 }}
        >
          <TraceLine status={i === lines.length - 1 ? "running" : undefined}>
            <TraceIcon>{i === lines.length - 1 ? <Spinner /> : <CheckIcon />}</TraceIcon>
            <TraceTitle>{t(line)}</TraceTitle>
          </TraceLine>
        </motion.div>
      ))}
    </Trace>
  )
}

function OptionCard({ option, index, onApply }: { option: AdviceOption; index: number; onApply?: () => void }) {
  const { t, lang } = useI18n()
  const reduce = useReducedMotion()
  const saves = option.saves_kzt !== null ? Number(option.saves_kzt) : null
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: reduce ? 0 : motionTokens.distance.md }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ ...springs.gentle, delay: index * motionTokens.stagger }}
      className="flex flex-col gap-3 rounded-lg border bg-card p-4 shadow-card"
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs text-muted-foreground">{t(CATEGORY[option.category])}</span>
        {saves !== null && saves > 0 && <span className="num text-sm font-medium text-ok">−{kzt(saves, lang)}</span>}
      </div>
      <div className="flex flex-col gap-1">
        <h3 className="text-[15px] font-medium text-pretty">{option.title}</h3>
        <p className="text-sm text-muted-foreground text-pretty">{option.why}</p>
      </div>
      {option.risk_before !== null && option.risk_after !== null && (
        <div className="grid grid-cols-2 gap-4 text-xs text-muted-foreground">
          <div className="flex flex-col gap-1.5">
            {t("whatif.nowLabel")}
            <RiskBar value={option.risk_before} />
          </div>
          <div className="flex flex-col gap-1.5">
            {t("whatif.afterLabel")}
            <RiskBar value={option.risk_after} />
          </div>
        </div>
      )}
      {onApply && (
        <Button variant="outline" size="sm" className="self-start" onClick={onApply}>
          {t("advice.apply")}
        </Button>
      )}
    </motion.li>
  )
}

export function AdviceSheet({
  machine,
  open,
  onOpenChange,
  toolApplies,
  onApply,
}: {
  machine: Machine
  open: boolean
  onOpenChange: (open: boolean) => void
  toolApplies: boolean
  onApply: (scenario: Scenario) => void
}) {
  const { t, lang } = useI18n()
  const mobile = useIsMobile()
  const advice = useQuery({
    queryKey: ["advice", machine.id, lang],
    enabled: open,
    staleTime: 5 * 60_000,
    queryFn: () => api<AdviceResponse>("/ai/advice", { method: "POST", json: { machine_id: machine.id, language: lang } }),
  })
  const apply = (option: AdviceOption) => {
    if (!option.scenario) return undefined
    return () => {
      onApply({ maintenance: option.scenario !== "tool", tool: option.scenario !== "maintenance", load: null })
      onOpenChange(false)
    }
  }
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side={mobile ? "bottom" : "right"}
        className={mobile ? "flex max-h-[88svh] flex-col gap-0 rounded-t-xl p-0" : "flex w-full flex-col gap-0 p-0 sm:max-w-md"}
      >
        <SheetHeader className="gap-2 border-b p-5">
          <SheetTitle className="display text-xl">{t("advice.title", { machine: machine.name })}</SheetTitle>
          <SheetDescription>{t("advice.lead")}</SheetDescription>
          {advice.data && <SourceBadge source={advice.data.source} degraded={advice.data.degraded} />}
        </SheetHeader>
        <div className="flex-1 overflow-y-auto p-5">
          {advice.isPending && <Working toolApplies={toolApplies} />}
          {advice.isError && (
            <div className="flex flex-col items-start gap-3 text-sm">
              <p>{t("advice.failed")}</p>
              <Button variant="outline" size="sm" onClick={() => advice.refetch()}>
                <RefreshCwIcon data-icon="inline-start" />
                {t("common.retry")}
              </Button>
            </div>
          )}
          <AnimatePresence mode="popLayout">
            {advice.data && (
              <motion.ul key="options" className="flex flex-col gap-3">
                {advice.data.options.map((option, index) => (
                  <OptionCard key={option.id} option={option} index={index} onApply={apply(option)} />
                ))}
              </motion.ul>
            )}
          </AnimatePresence>
          {advice.data && <p className="mt-5 text-xs text-muted-foreground text-pretty">{t("advice.footnote")}</p>}
        </div>
      </SheetContent>
    </Sheet>
  )
}
