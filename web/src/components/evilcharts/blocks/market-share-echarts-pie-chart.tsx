import { useState } from "react"
import {
  EChartsPieChart,
  type ChartConfig,
} from "@/components/evilcharts/charts/echarts-pie-chart"
import { useI18n } from "@/i18n"
import type { Machine, RankingItem } from "@/lib/types"
import { riskLevel } from "@/lib/levels"

export function EChartsMarketSharePieChart({
  machines,
  ranking,
}: {
  machines: Machine[]
  ranking: RankingItem[]
}) {
  const { lang } = useI18n()
  const kk = lang === "kk"
  const [selected, setSelected] = useState<string | null>(null)
  const series = [
    { key: "normal", label: kk ? "Қалыпты" : "В норме", color: "#4a9eff" },
    {
      key: "warning",
      label: kk ? "Назар аудару" : "Внимание",
      color: "#b79b6b",
    },
    {
      key: "critical",
      label: kk ? "Жоғары тәуекел" : "Высокий риск",
      color: "#ff7a2e",
    },
    {
      key: "unknown",
      label: kk ? "Бағаланбаған" : "Без оценки",
      color: "#64748b",
    },
  ].map((item) => ({
    ...item,
    value: machines.filter((machine) => {
      const score = ranking.find((row) => row.machine_id === machine.id)?.score
      return (score ? riskLevel(score.risk_index) : "unknown") === item.key
    }).length,
  }))
  const config = Object.fromEntries(
    series.map((item) => [
      item.key,
      {
        label: item.label,
        colors: { light: [item.color], dark: [item.color] },
      },
    ])
  ) satisfies ChartConfig
  const data = series
    .filter((item) => item.value > 0)
    .map((item) => ({ state: item.key, value: item.value }))
  const selection = series.find((item) => item.key === selected)
  return (
    <div className="flex h-full min-w-0 flex-col gap-4">
      <div>
        <h3 className="text-base font-medium">
          {kk ? "Жабдықтар күйі" : "Состояние парка"}
        </h3>
        <p className="mt-1 text-xs text-muted-foreground">
          {kk ? "Соңғы тәуекел бағасы бойынша" : "По последней оценке риска"}
        </p>
      </div>
      <div className="relative h-[208px] w-full">
        {machines.length ? (
          <>
            <EChartsPieChart
              className="h-full w-full"
              data={data}
              config={config}
              dataKey="value"
              nameKey="state"
              selectedSector={selected}
              onSelectionChange={(item) => setSelected(item?.dataKey ?? null)}
              animation={false}
            >
              <EChartsPieChart.Tooltip />
              <EChartsPieChart.Pie
                isClickable
                innerRadius="70%"
                outerRadius="92%"
                paddingAngle={3}
              />
            </EChartsPieChart>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <strong className="num text-4xl font-medium">
                {selection?.value ?? machines.length}
              </strong>
              <span className="mt-1 text-xs text-muted-foreground">
                {selection?.label ?? (kk ? "жабдық" : "единиц оборудования")}
              </span>
            </div>
          </>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            {kk ? "Жабдық қосыңыз" : "Добавьте оборудование"}
          </div>
        )}
      </div>
      <div className="grid gap-2 border-t pt-4">
        {series.map((item) => (
          <button
            key={item.key}
            type="button"
            aria-pressed={selected === item.key}
            disabled={!item.value}
            onClick={() => setSelected(selected === item.key ? null : item.key)}
            className={`flex items-center gap-2 text-left text-xs transition-opacity disabled:cursor-default ${selected && selected !== item.key ? "opacity-40" : ""}`}
          >
            <span
              className="size-2 shrink-0 rounded-sm"
              style={{ background: item.color }}
            />
            <span>{item.label}</span>
            <span className="num ml-auto text-muted-foreground">
              {item.value}
            </span>
            <span className="num w-10 text-right text-muted-foreground">
              {machines.length
                ? Math.round((item.value / machines.length) * 100)
                : 0}
              %
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
