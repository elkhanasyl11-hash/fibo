import { useMutation, useQueryClient } from "@tanstack/react-query"
import { CheckIcon, ClipboardCopyIcon, RotateCcwIcon } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
  InputGroupText,
} from "@/components/ui/input-group"
import { Slider } from "@/components/ui/slider"
import { Spinner } from "@/components/ui/spinner"
import { useI18n } from "@/i18n"
import { api, ApiError } from "@/lib/api"
import { date, num } from "@/lib/format"
import { useMachineSummary } from "@/lib/queries"
import type { Machine, ProfileConfig, Reading } from "@/lib/types"

const BASE = [
  { name: "operating_hours", unit: "ч" },
  { name: "load_pct", unit: "%" },
  { name: "temperature_c", unit: "°C" },
  { name: "spindle_rpm", unit: "об/мин" },
] as const

export function ReadingsForm({
  machine,
  profile,
}: {
  machine: Machine
  profile: ProfileConfig
}) {
  const { t, lang } = useI18n()
  const kk = lang === "kk"
  const client = useQueryClient()
  const summary = useMachineSummary(machine.id)
  const latest = summary.data?.recent_readings[0]
  const [values, setValues] = useState<Record<string, string>>({})
  const [lastSaved, setLastSaved] = useState<Reading | null>(null)
  const ranges = profile.reading_ranges
  const fields = [
    ...BASE.filter((field) => field.name in ranges).map((field) => ({
      name: field.name as string,
      label: t(`field.${field.name}`),
      unit: field.unit,
      extra: false,
    })),
    ...profile.extra_fields.map((field) => ({
      name: field.name,
      label: kk && field.title_kk ? field.title_kk : field.title_ru,
      unit: field.unit,
      extra: true,
    })),
  ]
  const parsed = (name: string) =>
    Number(values[name]?.trim().replace(",", "."))
  const errorOf = (name: string) => {
    const raw = values[name]?.trim()
    if (!raw) return null
    const value = parsed(name)
    if (!Number.isFinite(value)) return t("form.notNumber")
    const range = ranges[name]
    return range && (value < range[0] || value > range[1])
      ? t("form.outOfRange", {
          min: num(range[0], 0, lang),
          max: num(range[1], 0, lang),
        })
      : null
  }
  const filled = fields.filter((field) => Boolean(values[field.name]?.trim()))
  const invalid = fields.some((field) => Boolean(errorOf(field.name)))
  const oldValue = (field: (typeof fields)[number]) =>
    field.extra
      ? latest?.extra?.[field.name]
      : latest?.[field.name as keyof Reading]
  const loadPrevious = () => {
    if (!latest) return
    setValues(
      Object.fromEntries(
        fields.flatMap((field) => {
          const value = oldValue(field)
          return typeof value === "number" ? [[field.name, String(value)]] : []
        })
      )
    )
    setLastSaved(null)
  }
  const save = useMutation({
    mutationFn: () => {
      const base = Object.fromEntries(
        filled
          .filter((field) => !field.extra)
          .map((field) => [field.name, parsed(field.name)])
      )
      const extra = Object.fromEntries(
        filled
          .filter((field) => field.extra)
          .map((field) => [field.name, parsed(field.name)])
      )
      // The API schedules the calculation. A second POST used to duplicate scores and could
      // report a failed save even when the reading had already been committed.
      return api<Reading>("/readings", {
        method: "POST",
        json: {
          machine_id: machine.id,
          source: "form",
          ...base,
          ...(Object.keys(extra).length ? { extra } : {}),
        },
      })
    },
    onSuccess: (reading) => {
      setLastSaved(reading)
      setValues({})
      client.invalidateQueries({ queryKey: ["machine-summary", machine.id] })
      client.invalidateQueries({ queryKey: ["readings", machine.id] })
      client.invalidateQueries({ queryKey: ["activity"] })
      client.invalidateQueries({ queryKey: ["ranking"] })
      client.invalidateQueries({ queryKey: ["risk-history", machine.id] })
      toast.success(t("reading.saved"))
    },
    onError: (error) =>
      toast.error(
        error instanceof ApiError && error.status === 422
          ? t("reading.invalid")
          : t("common.error")
      ),
  })
  const change = (name: string, value: string) => {
    setValues((current) => ({ ...current, [name]: value }))
    setLastSaved(null)
    save.reset()
  }
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        if (!invalid && filled.length && !save.isPending) save.mutate()
      }}
      className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_280px]"
    >
      <div className="flex min-w-0 flex-col gap-6">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-4">
          <span className="text-sm text-muted-foreground">
            {kk
              ? "Кемінде бір көрсеткішті енгізіңіз"
              : "Заполните хотя бы один показатель"}
          </span>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!latest || save.isPending}
            onClick={loadPrevious}
          >
            <ClipboardCopyIcon />
            {kk ? "Соңғы өлшемді алу" : "Взять последние"}
          </Button>
        </div>
        <FieldGroup className="grid gap-6 sm:grid-cols-2">
          {fields.map((field) => {
            const error = errorOf(field.name)
            const range = ranges[field.name]
            const previous = oldValue(field)
            return (
              <Field key={field.name} data-invalid={error ? true : undefined}>
                <div className="flex items-center justify-between gap-2">
                  <FieldLabel htmlFor={`rf-${field.name}`}>
                    {field.label}
                  </FieldLabel>
                  {typeof previous === "number" && (
                    <span className="num text-xs text-muted-foreground">
                      {kk ? "Бұрын" : "Было"}{" "}
                      {num(previous, previous % 1 ? 1 : 0, lang)}
                    </span>
                  )}
                </div>
                <InputGroup className="h-12 rounded-md">
                  <InputGroupInput
                    disabled={save.isPending}
                    id={`rf-${field.name}`}
                    inputMode="decimal"
                    className="num text-base"
                    aria-describedby={`rf-help-${field.name}`}
                    aria-invalid={error ? true : undefined}
                    value={values[field.name] ?? ""}
                    onChange={(event) => change(field.name, event.target.value)}
                  />
                  <InputGroupAddon align="inline-end">
                    <InputGroupText>{field.unit}</InputGroupText>
                  </InputGroupAddon>
                </InputGroup>
                {range && (
                  <p
                    id={`rf-help-${field.name}`}
                    className="text-xs text-muted-foreground"
                  >
                    {kk ? "Енгізу аралығы" : "Диапазон ввода"}:{" "}
                    {num(range[0], 0, lang)}–{num(range[1], 0, lang)}{" "}
                    {field.unit}
                  </p>
                )}
                {range &&
                  ["load_pct", "temperature_c"].includes(field.name) && (
                    <Slider
                      aria-label={`${field.label}: ${kk ? "жүгірткі" : "ползунок"}`}
                      min={range[0]}
                      max={range[1]}
                      step={1}
                      disabled={save.isPending}
                      value={[
                        Number.isFinite(parsed(field.name)) &&
                        values[field.name]?.trim()
                          ? Math.max(
                              range[0],
                              Math.min(range[1], parsed(field.name))
                            )
                          : range[0],
                      ]}
                      onValueChange={([value]) =>
                        change(field.name, String(value))
                      }
                      className="py-2"
                    />
                  )}
                {error && <FieldError>{error}</FieldError>}
              </Field>
            )
          })}
        </FieldGroup>
      </div>
      <aside className="flex h-fit flex-col gap-5 rounded-xl border bg-muted/20 p-5 xl:sticky xl:top-20">
        <div>
          <h3 className="text-sm font-medium">{machine.name}</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            {kk ? "Өлшемді сақтау" : "Сохранение замера"}
          </p>
        </div>
        <div className="flex items-baseline justify-between">
          <strong className="num text-3xl font-medium">
            {filled.length}
            <span className="text-lg text-muted-foreground">
              {" "}
              / {fields.length}
            </span>
          </strong>
          <span className="text-xs text-muted-foreground">
            {kk ? "көрсеткіш" : "показателей"}
          </span>
        </div>
        <div className="flex gap-1" aria-hidden>
          {fields.map((field) => (
            <span
              key={field.name}
              className={`h-1 flex-1 rounded ${errorOf(field.name) ? "bg-crit" : values[field.name]?.trim() ? "bg-primary" : "bg-border"}`}
            />
          ))}
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          {kk
            ? "Деректер сақталғаннан кейін тәуекел автоматты түрде қайта есептеледі."
            : "После сохранения Fibo автоматически пересчитает риск по новым показаниям."}
        </p>
        {save.isError && (
          <p role="alert" className="text-xs text-destructive">
            {kk
              ? "Сақтау орындалмады. Деректерді тексеріп, қайталаңыз."
              : "Замер не сохранён. Проверьте данные и повторите попытку."}
          </p>
        )}
        {lastSaved && (
          <p role="status" className="flex items-start gap-2 text-xs text-ok">
            <CheckIcon className="size-4 shrink-0" />
            {kk ? "Сақталды" : "Сохранено"} ·{" "}
            {date(lastSaved.recorded_at, lang, true)}
          </p>
        )}
        <Button
          type="submit"
          size="lg"
          className="w-full rounded-md"
          disabled={!filled.length || invalid || save.isPending}
        >
          {save.isPending ? <Spinner /> : <CheckIcon />}
          {t("common.save")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          className="rounded-md"
          disabled={!filled.length || save.isPending}
          onClick={() => {
            setValues({})
            save.reset()
          }}
        >
          <RotateCcwIcon />
          {kk ? "Тазалау" : "Очистить поля"}
        </Button>
      </aside>
    </form>
  )
}
