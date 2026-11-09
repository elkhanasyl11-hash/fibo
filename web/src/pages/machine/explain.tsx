import { motion, useReducedMotion } from "motion/react"

import { Hint } from "@/components/hint"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { useI18n } from "@/i18n"
import { num } from "@/lib/format"
import { motionTokens } from "@/lib/motion"
import type { RiskScore } from "@/lib/types"

function Bar({
  label,
  value,
  max,
  positive,
  text,
  delay,
}: {
  label: string
  value: number
  max: number
  positive: boolean
  text: string
  delay: number
}) {
  const reduce = useReducedMotion()
  const width = max > 0 ? Math.min(Math.abs(value) / max, 1) : 0
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_minmax(80px,1.2fr)_56px] items-center gap-3 text-sm">
      <span className="truncate" title={label}>
        {label}
      </span>
      <div className="relative h-2 rounded-full bg-surface">
        <motion.span
          className="absolute inset-y-0 left-0 w-full origin-left rounded-full"
          style={{
            background: positive ? "var(--crit)" : "var(--ok)",
            opacity: 0.85,
          }}
          initial={{ scaleX: reduce ? width : 0 }}
          animate={{ scaleX: width }}
          transition={{
            duration: motionTokens.duration.slow,
            ease: motionTokens.easing.smooth,
            delay,
          }}
        />
      </div>
      <span className="num text-right text-muted-foreground">{text}</span>
    </div>
  )
}

// SHAP factors of the failure model (log-odds: positive = pushes risk up) and the weighted
// signals of the risk index (value × weight = share of the index).
export function RiskExplanation({ score }: { score: RiskScore }) {
  const { t, lang } = useI18n()
  const shap = score.shap_top3
  const maxShap = Math.max(...shap.map((f) => Math.abs(f.contribution)), 0.0001)
  const signals = score.signals.filter((s) => s.weight > 0)
  const maxSignal = Math.max(
    ...signals.map((s) => (s.value ?? 0) * s.weight),
    0.0001
  )
  const reasonText: Record<string, string> =
    lang === "kk"
      ? {
          tool_changed_at: "Модель үшін құралды ауыстыру күні қажет",
          recent_reading_with_spindle_rpm_and_load_pct:
            "Айналым мен жүктеме көрсетілген жаңа өлшем қажет",
          risk_model_not_loaded: "Тәуекел моделі серверде жүктелмеген",
          model_not_applicable_for_profile:
            "Бұл өндіріс түрі үшін модель қолданылмайды",
        }
      : {
          tool_changed_at: "Для модели нужна дата последней смены инструмента",
          recent_reading_with_spindle_rpm_and_load_pct:
            "Нужен свежий замер с оборотами шпинделя и нагрузкой",
          risk_model_not_loaded: "Модель отказа не загружена на сервере",
          model_not_applicable_for_profile:
            "Модель отказа не применяется к этому профилю производства",
        }
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1 text-base font-medium">
          {t("explain.title")}
          <Hint text={t("hint.explain")} />
        </CardTitle>
        <CardDescription>{t("explain.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {shap.length > 0 && (
          <section className="flex flex-col gap-3">
            <h3 className="text-sm text-muted-foreground">
              {t("explain.shap")}
            </h3>
            {shap.map((factor, i) => (
              <Bar
                key={factor.feature}
                label={factor.title_ru}
                value={factor.contribution}
                max={maxShap}
                positive={factor.contribution > 0}
                text={`${factor.contribution > 0 ? "+" : "−"}${num(Math.abs(factor.contribution), 2, lang)}`}
                delay={i * motionTokens.stagger}
              />
            ))}
          </section>
        )}
        {shap.length === 0 && score.model_not_used_reasons.length > 0 && (
          <p className="rounded-md bg-surface px-3 py-2 text-sm text-muted-foreground">
            {score.model_not_used_reasons
              .map((reason) => reasonText[reason] ?? t("explain.noModel"))
              .join(". ")}
          </p>
        )}
        <section className="flex flex-col gap-3">
          <h3 className="text-sm text-muted-foreground">
            {t("explain.signals")}
          </h3>
          {signals.map((signal, i) => (
            <Bar
              key={signal.name}
              label={signal.title_ru}
              value={(signal.value ?? 0) * signal.weight}
              max={maxSignal}
              positive
              text={
                signal.value === null
                  ? t("explain.noSignal")
                  : num((signal.value ?? 0) * signal.weight, 2, lang)
              }
              delay={i * motionTokens.stagger}
            />
          ))}
        </section>
      </CardContent>
    </Card>
  )
}
