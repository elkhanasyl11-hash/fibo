import { motion, useReducedMotion } from "motion/react"

import { Hint } from "@/components/hint"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useI18n } from "@/i18n"
import { motionTokens } from "@/lib/motion"
import type { ReportSummary } from "@/lib/types"

const MAX_ROWS = 5

// Most frequent causes on incident cards of the last 30 days (backend report): which failures repeat.
export function TopCauses({ report, pending }: { report: ReportSummary | undefined; pending: boolean }) {
  const { t } = useI18n()
  const reduce = useReducedMotion()
  const causes = (report?.top_causes ?? []).slice(0, MAX_ROWS)
  const max = Math.max(...causes.map((c) => c.count), 1)
  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle className="flex items-center gap-1 text-base font-medium">
          {t("causes.title")}
          <Hint text={t("hint.causes")} />
        </CardTitle>
        <CardDescription>
          {report ? t("causes.lead", { incidents: report.totals.incidents, failures: report.totals.failures }) : "—"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {pending ? (
          <Skeleton className="h-40 w-full" />
        ) : causes.length === 0 ? (
          <p className="text-sm text-muted-foreground text-pretty">{t("causes.empty")}</p>
        ) : (
          <ol className="flex flex-col gap-3">
            {causes.map((cause, i) => (
              <li key={cause.cause} className="flex flex-col gap-1.5 text-sm">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="line-clamp-2 text-pretty">{cause.cause}</span>
                  <span className="num shrink-0 text-muted-foreground">{cause.count}</span>
                </div>
                <div className="h-1.5 rounded-full bg-surface">
                  <motion.div
                    className={i === 0 ? "h-full rounded-full bg-primary" : "h-full rounded-full bg-foreground/40"}
                    style={{ width: `${(cause.count / max) * 100}%`, originX: 0 }}
                    initial={{ scaleX: reduce ? 1 : 0 }}
                    animate={{ scaleX: 1 }}
                    transition={{ duration: motionTokens.duration.slow, ease: motionTokens.easing.smooth, delay: i * motionTokens.stagger }}
                  />
                </div>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  )
}
