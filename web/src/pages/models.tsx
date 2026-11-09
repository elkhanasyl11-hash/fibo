import { Hint } from "@/components/hint"
import { PageHeader } from "@/components/page-header"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useI18n } from "@/i18n"
import { num } from "@/lib/format"

// Only measured numbers: backend/ml/artifacts/metrics.json and audio_metrics.json (README, Metrics).
const FAILURE = { rocAuc: 0.976, prAuc: 0.735, brierRaw: 0.0205, brierCal: 0.0139, precision: 0.84, recall: 0.63 }
const AUDIO_BY_ID = [
  { id: "id_00", auc: 0.82 },
  { id: "id_02", auc: 0.68 },
  { id: "id_04", auc: 0.61 },
  { id: "id_06", auc: 0.42 },
]
const AUDIO_MEAN = 0.63

function Metric({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="flex flex-col gap-2">
      <dt className="flex items-center gap-1 text-sm text-muted-foreground">
        {label}
        <Hint text={hint} />
      </dt>
      <dd className="num display text-[28px] leading-none">{value}</dd>
    </div>
  )
}

export function ModelsPage() {
  const { t, lang } = useI18n()
  const f = (v: number, d = 3) => num(v, d, lang)
  return (
    <>
      <PageHeader title={t("models.title")} description={t("models.lead")} />
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium">{t("models.failureTitle")}</CardTitle>
          <CardDescription>{t("models.failureLead")}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <dl className="grid grid-cols-2 gap-6 sm:grid-cols-3 lg:grid-cols-5">
            <Metric label="ROC-AUC" value={f(FAILURE.rocAuc)} hint={t("models.rocHint")} />
            <Metric label="PR-AUC" value={f(FAILURE.prAuc)} hint={t("models.prHint")} />
            <Metric label="Brier" value={`${f(FAILURE.brierRaw, 4)} → ${f(FAILURE.brierCal, 4)}`} hint={t("models.brierHint")} />
            <Metric label="Precision" value={f(FAILURE.precision, 2)} hint={t("models.precisionHint")} />
            <Metric label="Recall" value={f(FAILURE.recall, 2)} hint={t("models.recallHint")} />
          </dl>
          <p className="text-sm text-muted-foreground text-pretty">{t("models.failureNote")}</p>
        </CardContent>
      </Card>
      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-medium">{t("models.audioTitle")}</CardTitle>
            <CardDescription>{t("models.audioLead")}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            <Metric label={t("models.audioMean")} value={f(AUDIO_MEAN, 2)} hint={t("models.audioHint")} />
            <ul className="flex flex-col gap-3">
              {AUDIO_BY_ID.map(({ id, auc }) => (
                <li key={id} className="grid grid-cols-[56px_1fr_40px] items-center gap-3 text-sm">
                  <span className="num text-muted-foreground">{id}</span>
                  <div className="relative h-2 rounded-full bg-surface">
                    <div className="absolute inset-y-0 left-0 rounded-full bg-foreground/60" style={{ width: `${auc * 100}%` }} />
                    <span className="absolute -inset-y-1 w-px bg-foreground/30" style={{ left: "50%" }} />
                  </div>
                  <span className="num text-right">{f(auc, 2)}</span>
                </li>
              ))}
            </ul>
            <p className="rounded-md bg-surface px-3 py-2 text-sm text-pretty">{t("models.audioHonest")}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-medium">{t("models.untestedTitle")}</CardTitle>
            <CardDescription>{t("models.untestedLead")}</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-4 text-sm">
              {(["models.u1", "models.u2", "models.u3"] as const).map((key) => (
                <li key={key} className="flex gap-3">
                  <span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-muted-foreground" />
                  <span className="text-pretty">{t(key)}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </>
  )
}
