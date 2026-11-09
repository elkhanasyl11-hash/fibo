import { ArrowRightIcon, TrendingDownIcon, TrendingUpIcon } from "lucide-react"
import { motion, useReducedMotion } from "motion/react"
import { useEffect, useRef, useState } from "react"

import { AnimatedNumber } from "@/components/animated-number"
import { RiskBar } from "@/components/risk-bar"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Slider } from "@/components/ui/slider"
import { Spinner } from "@/components/ui/spinner"
import { Toggle } from "@/components/ui/toggle"
import { useI18n } from "@/i18n"
import { api, ApiError } from "@/lib/api"
import { kzt, num } from "@/lib/format"
import { levelVar, riskLevel } from "@/lib/levels"
import { motionTokens, springs } from "@/lib/motion"
import { useMachineSummary } from "@/lib/queries"
import type { Machine, ProfileConfig, WhatIfResponse } from "@/lib/types"
import { cn } from "@/lib/utils"

const DEBOUNCE_MS = 250

interface Overrides {
  maintenance_done: boolean
  tool_wear_min: number | null
  spindle_rpm: number | null
  load_pct: number | null
  temperature_c: number | null
}

// Half-circle gauge of the risk index; the needle swings to the scenario value.
function Gauge({ value }: { value: number }) {
  const reduce = useReducedMotion()
  const level = riskLevel(value) ?? "normal"
  return (
    <svg viewBox="0 0 120 70" className="w-40" aria-hidden>
      <path d="M10 60 A50 50 0 0 1 110 60" fill="none" stroke="var(--surface)" strokeWidth="10" strokeLinecap="round" />
      <motion.path
        d="M10 60 A50 50 0 0 1 110 60"
        fill="none"
        stroke={levelVar[level]}
        strokeWidth="10"
        strokeLinecap="round"
        initial={false}
        animate={{ pathLength: Math.max(value, 0.02) }}
        transition={reduce ? { duration: 0 } : springs.gentle}
      />
    </svg>
  )
}

export function Simulator({ machine, profile }: { machine: Machine; profile: ProfileConfig | undefined }) {
  const { t, lang } = useI18n()
  const summary = useMachineSummary(machine.id)
  const latest = summary.data?.recent_readings[0]
  const ranges = profile?.reading_ranges ?? {}
  const toolApplies = profile?.id === "metalworking"
  const [o, setO] = useState<Overrides>({ maintenance_done: false, tool_wear_min: null, spindle_rpm: null, load_pct: null, temperature_c: null })
  const [result, setResult] = useState<WhatIfResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const controller = useRef<AbortController | null>(null)

  useEffect(() => {
    const id = setTimeout(async () => {
      controller.current?.abort()
      const abort = new AbortController()
      controller.current = abort
      setBusy(true)
      try {
        const overrides = Object.fromEntries(Object.entries(o).filter(([, v]) => v !== null && v !== false))
        const data = await api<WhatIfResponse>("/risk-scores/what-if", {
          method: "POST",
          json: { machine_id: machine.id, overrides: { maintenance_done: o.maintenance_done, ...overrides } },
          signal: abort.signal,
        })
        setResult(data)
        setError(null)
      } catch (e) {
        if (abort.signal.aborted) return
        setError(e instanceof ApiError && e.status === 422 ? t("sim.invalid") : t("common.error"))
      } finally {
        if (!abort.signal.aborted) setBusy(false)
      }
    }, DEBOUNCE_MS)
    return () => clearTimeout(id)
  }, [o, machine.id, t])

  const slider = (key: keyof Overrides, label: string, unit: string, current: number | null | undefined, min: number, max: number, step: number) => {
    const chosen = o[key] as number | null
    const value = chosen ?? current ?? min
    return (
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between text-sm">
          <span>{label}</span>
          <span className="num text-muted-foreground">
            {chosen === null && current == null ? t("sim.unset") : `${num(value, 0, lang)} ${unit}`}
            {current != null && <> · {t("whatif.now", { v: num(current, 0, lang) })}</>}
          </span>
        </div>
        <Slider min={min} max={max} step={step} value={[value]} onValueChange={([v]) => setO((s) => ({ ...s, [key]: v }))} aria-label={label} className="py-2" />
      </div>
    )
  }

  const before = result?.current
  const after = result?.scenario
  const deltaKzt = before && after ? Number(after.priority_kzt) - Number(before.priority_kzt) : 0
  const deltaRisk = before && after ? after.risk_index - before.risk_index : 0

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium">{t("sim.controls")}</CardTitle>
          <CardDescription>{t("sim.controlsLead")}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <Toggle variant="outline" className="h-11 w-fit" pressed={o.maintenance_done} onPressedChange={(v) => setO((s) => ({ ...s, maintenance_done: v }))}>
            {t("whatif.maintenance")}
          </Toggle>
          {toolApplies && slider("tool_wear_min", t("sim.toolWear"), t("sim.min"), null, 0, 250, 5)}
          {"spindle_rpm" in ranges && slider("spindle_rpm", t("field.spindle_rpm"), "об/мин", latest?.spindle_rpm, ranges.spindle_rpm[0], Math.min(ranges.spindle_rpm[1], 6000), 50)}
          {"load_pct" in ranges && slider("load_pct", t("field.load_pct"), "%", latest?.load_pct, 0, Math.min(ranges.load_pct[1], 150), 5)}
          {"temperature_c" in ranges && slider("temperature_c", t("field.temperature_c"), "°C", latest?.temperature_c, Math.max(ranges.temperature_c[0], 0), Math.min(ranges.temperature_c[1], 300), 1)}
          <p className="text-xs text-muted-foreground">{t("sim.note")}</p>
        </CardContent>
      </Card>
      <Card className={cn(after && riskLevel(after.risk_index) === "critical" && "shadow-glow-crit")}>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base font-medium">
            {t("sim.result")}
            {busy && <Spinner className="size-3.5" />}
          </CardTitle>
          <CardDescription>{t("sim.resultLead", { machine: machine.name })}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col items-center gap-6">
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="flex flex-col items-center">
            <Gauge value={after?.risk_index ?? before?.risk_index ?? 0} />
            <span className="num display -mt-6 text-4xl">
              <AnimatedNumber value={after?.risk_index ?? 0} format={(v) => num(v, 2, lang)} />
            </span>
            <span className="mt-1 text-xs text-muted-foreground">{t("risk.index")}</span>
          </div>
          <div className="grid w-full grid-cols-[1fr_auto_1fr] items-center gap-3 rounded-lg bg-surface p-4">
            <div className="flex flex-col gap-2">
              <span className="text-xs text-muted-foreground">{t("sim.was")}</span>
              <RiskBar value={before?.risk_index ?? null} />
              <span className="num text-sm">{kzt(before?.priority_kzt, lang)}</span>
            </div>
            <motion.span animate={{ x: [0, motionTokens.distance.xs, 0] }} transition={{ duration: motionTokens.duration.slow }} key={after?.risk_index}>
              <ArrowRightIcon className="size-4 text-muted-foreground" />
            </motion.span>
            <div className="flex flex-col gap-2">
              <span className="text-xs text-muted-foreground">{t("sim.will")}</span>
              <RiskBar value={after?.risk_index ?? null} />
              <span className="num text-sm">{kzt(after?.priority_kzt, lang)}</span>
            </div>
          </div>
          {after && (
            <p className={cn("flex items-center gap-2 text-sm", deltaKzt < 0 ? "text-ok" : deltaKzt > 0 ? "text-crit" : "text-muted-foreground")}>
              {deltaKzt < 0 ? <TrendingDownIcon className="size-4" /> : deltaKzt > 0 ? <TrendingUpIcon className="size-4" /> : null}
              {deltaKzt === 0
                ? t("whatif.noChange")
                : t(deltaKzt < 0 ? "sim.less" : "sim.more", { kzt: kzt(Math.abs(deltaKzt), lang), risk: num(Math.abs(deltaRisk), 2, lang) })}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
