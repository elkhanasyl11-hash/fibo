import { useQuery } from "@tanstack/react-query"
import { ArrowRightIcon, LightbulbIcon } from "lucide-react"
import { useEffect, useState } from "react"

import { AnimatedNumber } from "@/components/animated-number"
import { Hint } from "@/components/hint"
import { RiskBar } from "@/components/risk-bar"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Slider } from "@/components/ui/slider"
import { Spinner } from "@/components/ui/spinner"
import { Toggle } from "@/components/ui/toggle"
import { useI18n } from "@/i18n"
import { api } from "@/lib/api"
import { kzt, num } from "@/lib/format"
import type { MachineSummary, WhatIfResponse } from "@/lib/types"
import { cn } from "@/lib/utils"

export interface Scenario {
  maintenance: boolean
  tool: boolean
  load: number | null
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return debounced
}

export function WhatIf({
  summary,
  toolApplies,
  scenario,
  onScenario,
  onAdvice,
}: {
  summary: MachineSummary
  toolApplies: boolean
  scenario: Scenario
  onScenario: (s: Scenario) => void
  onAdvice: () => void
}) {
  const { t, lang } = useI18n()
  const currentLoad = summary.recent_readings.find((r) => r.load_pct !== null)?.load_pct ?? null
  const debounced = useDebounced(scenario, 300)
  const touched = debounced.maintenance || debounced.tool || (debounced.load !== null && debounced.load !== currentLoad)
  const result = useQuery({
    queryKey: ["what-if", summary.machine.id, debounced],
    enabled: touched,
    placeholderData: (previous) => previous,
    queryFn: () =>
      api<WhatIfResponse>("/risk-scores/what-if", {
        method: "POST",
        json: {
          machine_id: summary.machine.id,
          overrides: {
            maintenance_done: debounced.maintenance,
            ...(debounced.tool ? { tool_wear_min: 0 } : {}),
            ...(debounced.load !== null && debounced.load !== currentLoad ? { load_pct: debounced.load } : {}),
          },
        },
      }),
  })
  const before = summary.latest_risk
  const after = touched ? result.data?.scenario : undefined
  const saves = before && after ? Number(before.priority_kzt) - Number(after.priority_kzt) : 0

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1 text-base font-medium">
          {t("whatif.title")}
          <Hint text={t("hint.whatif")} />
        </CardTitle>
        <CardDescription>{t("whatif.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <div className="flex flex-wrap gap-2">
          <Toggle variant="outline" pressed={scenario.maintenance} onPressedChange={(maintenance) => onScenario({ ...scenario, maintenance })}>
            {t("whatif.maintenance")}
          </Toggle>
          {toolApplies && (
            <Toggle variant="outline" pressed={scenario.tool} onPressedChange={(tool) => onScenario({ ...scenario, tool })}>
              {t("whatif.tool")}
            </Toggle>
          )}
        </div>
        {currentLoad !== null && (
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between text-sm">
              <span>{t("whatif.load")}</span>
              <span className="num text-muted-foreground">
                {num(scenario.load ?? currentLoad)}% · {t("whatif.now", { v: num(currentLoad) })}
              </span>
            </div>
            <Slider
              min={0}
              max={120}
              step={5}
              value={[scenario.load ?? currentLoad]}
              onValueChange={([v]) => onScenario({ ...scenario, load: v })}
              aria-label={t("whatif.load")}
            />
          </div>
        )}
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3 rounded-lg bg-surface p-4">
          <div className="flex min-w-0 flex-col gap-2">
            <span className="text-xs text-muted-foreground">{t("whatif.nowLabel")}</span>
            <RiskBar value={before?.risk_index ?? null} />
            <span className="num text-sm">{kzt(before?.priority_kzt, lang)}</span>
          </div>
          <ArrowRightIcon className="size-4 text-muted-foreground" />
          <div className={cn("flex min-w-0 flex-col gap-2", !after && "opacity-50")}>
            <span className="flex items-center gap-2 text-xs text-muted-foreground">
              {t("whatif.afterLabel")}
              {result.isFetching && <Spinner className="size-3" />}
            </span>
            <RiskBar value={after?.risk_index ?? before?.risk_index ?? null} />
            <span className="text-sm">
              {after ? <AnimatedNumber value={Number(after.priority_kzt)} format={(v) => kzt(v, lang)} /> : "—"}
            </span>
          </div>
        </div>
        {after && (
          <p className="text-sm">
            {saves > 0 ? (
              <>
                {t("whatif.saves")} <span className="num font-medium text-ok"><AnimatedNumber value={saves} format={(v) => kzt(v, lang)} /></span>
              </>
            ) : (
              <span className="text-muted-foreground">{t("whatif.noChange")}</span>
            )}
          </p>
        )}
      </CardContent>
      <CardFooter className="justify-between gap-3">
        <span className="text-xs text-muted-foreground">{t("whatif.notSaved")}</span>
        <Button onClick={onAdvice}>
          <LightbulbIcon data-icon="inline-start" />
          {t("advice.open")}
        </Button>
      </CardFooter>
    </Card>
  )
}
