import {
  ArrowDownRightIcon,
  ArrowUpRightIcon,
  ClipboardPenIcon,
} from "lucide-react"
import { Link } from "react-router"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useI18n } from "@/i18n"
import { date, num } from "@/lib/format"
import type { MachineSummary, ProfileConfig } from "@/lib/types"

export function MachineTelemetry({
  summary,
  profile,
}: {
  summary: MachineSummary
  profile?: ProfileConfig
}) {
  const { lang, t } = useI18n()
  const kk = lang === "kk"
  const latest = summary.recent_readings[0]
  const previous = summary.recent_readings[1]
  const base = [
    { key: "temperature_c", label: t("field.temperature_c"), unit: "°C" },
    { key: "load_pct", label: t("field.load_pct"), unit: "%" },
    {
      key: "spindle_rpm",
      label: t("field.spindle_rpm"),
      unit: kk ? "айн/мин" : "об/мин",
    },
    {
      key: "operating_hours",
      label: t("field.operating_hours"),
      unit: t("unit.h"),
    },
  ]
  const fields = [
    ...base.filter((field) => !profile || field.key in profile.reading_ranges),
    ...(profile?.extra_fields ?? []).map((field) => ({
      key: field.name,
      label: kk && field.title_kk ? field.title_kk : field.title_ru,
      unit: field.unit,
    })),
  ]
  const valueOf = (row: typeof latest, key: string): number | null => {
    if (!row) return null
    const value = key in row ? row[key as keyof typeof row] : row.extra?.[key]
    return typeof value === "number" ? value : null
  }
  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-3">
        <div>
          <CardTitle className="text-base font-medium">
            {kk ? "Соңғы көрсеткіштер" : "Последние показания"}
          </CardTitle>
          <p className="mt-1 text-xs text-muted-foreground">
            {latest
              ? date(latest.recorded_at, lang, true)
              : kk
                ? "Өлшемдер әлі жоқ"
                : "Замеров пока нет"}
            {latest && (
              <>
                {" "}
                ·{" "}
                {latest.source === "panel"
                  ? kk
                    ? "Панель фотосы"
                    : "Фото панели"
                  : latest.source === "bot"
                    ? "Telegram"
                    : kk
                      ? "Қолмен енгізілді"
                      : "Ручной ввод"}
              </>
            )}
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link to={`/app/input?tab=readings&machine=${summary.machine.id}`}>
            <ClipboardPenIcon />
            {kk ? "Өлшем қосу" : "Добавить замер"}
          </Link>
        </Button>
      </CardHeader>
      <CardContent>
        <dl className="grid grid-cols-2 gap-6 lg:grid-cols-4">
          {fields.map((field) => {
            const value = valueOf(latest, field.key)
            const before = valueOf(previous, field.key)
            const diff =
              value !== null && before !== null ? value - before : null
            return (
              <div
                key={field.key}
                className="flex flex-col gap-2 border-l pl-4 first:border-l-0 first:pl-0"
              >
                <dt className="text-xs text-muted-foreground">{field.label}</dt>
                <dd className="num text-2xl font-medium">
                  {value === null ? "—" : num(value, value % 1 ? 1 : 0, lang)}{" "}
                  <span className="text-xs font-normal text-muted-foreground">
                    {field.unit}
                  </span>
                </dd>
                {diff !== null && (
                  <span className="num flex items-center gap-1 text-xs text-muted-foreground">
                    {diff > 0 ? (
                      <ArrowUpRightIcon className="size-3" />
                    ) : diff < 0 ? (
                      <ArrowDownRightIcon className="size-3" />
                    ) : null}
                    {diff > 0 ? "+" : ""}
                    {num(diff, 1, lang)}{" "}
                    {kk ? "алдыңғы өлшеммен" : "к предыдущему замеру"}
                  </span>
                )}
              </div>
            )
          })}
        </dl>
      </CardContent>
    </Card>
  )
}
