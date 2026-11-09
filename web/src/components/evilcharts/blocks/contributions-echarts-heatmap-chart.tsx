import { useMemo, useState } from "react"
import {
  EChartsHeatmapChart,
  type ChartConfig,
} from "@/components/evilcharts/charts/echarts-heatmap-chart"
import { useI18n } from "@/i18n"
import type { ActivityResponse } from "@/lib/types"

export function EChartsContributionsHeatmapChart({
  activity,
  loading = false,
}: {
  activity?: ActivityResponse
  loading?: boolean
}) {
  const { lang } = useI18n()
  const kk = lang === "kk"
  const [metric, setMetric] = useState<"readings" | "incidents" | "resolved">(
    "readings"
  )
  const [selected, setSelected] = useState<string | null>(null)
  const labels = {
    readings: kk ? "Замеры" : "Замеры",
    incidents: kk ? "Оқиғалар" : "Инциденты",
    resolved: kk ? "Шешілген" : "Устранено",
  }
  const data = useMemo(
    () =>
      (activity?.days ?? []).map((day) => ({
        date: day.date,
        value: day[metric],
      })),
    [activity, metric]
  )
  const total = data.reduce((sum, day) => sum + day.value, 0)
  const config = {
    activity: {
      label: labels[metric],
      colors: {
        light: ["#dceaff", "#9bc6fa", "#4a9eff", "#1a64bb"],
        dark: ["#173254", "#24568d", "#3885d6", "#65b0ff"],
      },
    },
  } satisfies ChartConfig
  const day = activity?.days.find((item) => item.date === selected)
  const months = kk
    ? [
        "Қаң",
        "Ақп",
        "Нау",
        "Сәу",
        "Мам",
        "Мау",
        "Шіл",
        "Там",
        "Қыр",
        "Қаз",
        "Қар",
        "Жел",
      ]
    : [
        "Янв",
        "Фев",
        "Мар",
        "Апр",
        "Май",
        "Июн",
        "Июл",
        "Авг",
        "Сен",
        "Окт",
        "Ноя",
        "Дек",
      ]
  return (
    <div className="flex h-full min-w-0 flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-base font-medium">
            {kk ? "Өндіріс белсенділігі" : "Активность производства"}
          </h3>
          <p className="mt-1 text-xs text-muted-foreground">
            {kk
              ? "Соңғы 12 ай · сақталған деректер"
              : "Последние 12 месяцев · сохранённые данные"}
          </p>
        </div>
        <div
          className="flex gap-1 rounded-md bg-muted p-1"
          role="group"
          aria-label={kk ? "Көрсеткіш" : "Показатель активности"}
        >
          {Object.entries(labels).map(([key, label]) => (
            <button
              key={key}
              type="button"
              aria-pressed={metric === key}
              onClick={() => setMetric(key as typeof metric)}
              className={`rounded px-3 py-1.5 text-xs transition-colors ${metric === key ? "bg-card text-foreground" : "text-muted-foreground hover:text-foreground"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex items-baseline gap-2">
        <strong className="num text-3xl font-medium">
          {loading ? "…" : total}
        </strong>
        <span className="text-xs text-muted-foreground">
          {labels[metric].toLowerCase()}
        </span>
      </div>
      <div className="overflow-x-auto pb-1">
        <EChartsHeatmapChart
          className="h-[168px] min-w-[560px]"
          data={data}
          config={config}
          range={activity ? [activity.from, activity.to] : undefined}
          weekStart="monday"
          animation={false}
          isLoading={loading}
          onSelectionChange={(value) => setSelected(value?.date ?? null)}
        >
          <EChartsHeatmapChart.Cell
            dataKey="activity"
            radius={2}
            gap={3}
            isClickable
          />
          <EChartsHeatmapChart.MonthLabel labels={months} />
          <EChartsHeatmapChart.DayLabel
            labels={
              kk
                ? ["", "Дс", "", "Ср", "", "Жм", ""]
                : ["", "Пн", "", "Ср", "", "Пт", ""]
            }
          />
          <EChartsHeatmapChart.Tooltip
            variant="default"
            dateFormatter={(date) =>
              new Date(`${date}T12:00:00`).toLocaleDateString(
                kk ? "kk-KZ" : "ru-RU",
                { day: "numeric", month: "long", year: "numeric" }
              )
            }
            valueFormatter={(value) =>
              `${value} · ${labels[metric].toLowerCase()}`
            }
          />
          <EChartsHeatmapChart.Legend
            lessLabel={kk ? "Аз" : "Меньше"}
            moreLabel={kk ? "Көп" : "Больше"}
          />
        </EChartsHeatmapChart>
      </div>
      <p className="min-h-5 text-xs text-muted-foreground" aria-live="polite">
        {day
          ? `${new Date(`${day.date}T12:00:00`).toLocaleDateString(kk ? "kk-KZ" : "ru-RU")} · ${day.readings} ${kk ? "өлшем" : "замеров"} · ${day.incidents} ${kk ? "оқиға" : "инцидентов"} · ${day.resolved} ${kk ? "шешілді" : "устранено"}`
          : kk
            ? "Күнді таңдап, сол күннің деректерін көріңіз"
            : "Выберите день, чтобы увидеть его показатели"}
      </p>
    </div>
  )
}
