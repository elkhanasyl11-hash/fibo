import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { InputGroup, InputGroupAddon, InputGroupInput, InputGroupText } from "@/components/ui/input-group"
import { Spinner } from "@/components/ui/spinner"
import { useI18n } from "@/i18n"
import { api, ApiError } from "@/lib/api"
import type { Machine, ProfileConfig } from "@/lib/types"

const BASE = [
  { name: "load_pct", unit: "%" },
  { name: "temperature_c", unit: "°C" },
  { name: "spindle_rpm", unit: "об/мин" },
  { name: "operating_hours", unit: "ч" },
] as const

export function ReadingDialog({ machine, profile, open, onOpenChange }: { machine: Machine; profile: ProfileConfig | undefined; open: boolean; onOpenChange: (o: boolean) => void }) {
  const { t, lang } = useI18n()
  const client = useQueryClient()
  const [values, setValues] = useState<Record<string, string>>({})
  const ranges = profile?.reading_ranges ?? {}
  const base = BASE.filter((f) => f.name in ranges)
  const extra = profile?.extra_fields ?? []
  const save = useMutation({
    mutationFn: async () => {
      const number = (k: string) => (values[k] === undefined || values[k] === "" ? undefined : Number(values[k]))
      const extraValues = Object.fromEntries(extra.map((f) => [f.name, number(f.name)]).filter(([, v]) => v !== undefined))
      await api("/readings", {
        method: "POST",
        json: {
          machine_id: machine.id,
          source: "form",
          ...Object.fromEntries(base.map((f) => [f.name, number(f.name)])),
          ...(Object.keys(extraValues).length ? { extra: extraValues } : {}),
        },
      })
      await api("/risk-scores/recompute", { method: "POST", json: { machine_id: machine.id } })
    },
    onSuccess: () => {
      client.invalidateQueries()
      toast.success(t("reading.saved"))
      setValues({})
      onOpenChange(false)
    },
    onError: (error) => toast.error(error instanceof ApiError && error.status === 422 ? t("reading.invalid") : t("common.error")),
  })
  const field = (name: string, label: string, unit: string) => {
    const range = ranges[name]
    return (
      <Field key={name}>
        <FieldLabel htmlFor={`r-${name}`}>{label}</FieldLabel>
        <InputGroup>
          <InputGroupInput
            id={`r-${name}`}
            type="number"
            inputMode="decimal"
            className="num"
            min={range?.[0]}
            max={range?.[1]}
            value={values[name] ?? ""}
            onChange={(e) => setValues((v) => ({ ...v, [name]: e.target.value }))}
          />
          <InputGroupAddon align="inline-end">
            <InputGroupText>{unit}</InputGroupText>
          </InputGroupAddon>
        </InputGroup>
      </Field>
    )
  }
  const filled = Object.values(values).some((v) => v !== "")
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("reading.title", { machine: machine.name })}</DialogTitle>
          <DialogDescription>{t("reading.lead")}</DialogDescription>
        </DialogHeader>
        <FieldGroup className="grid gap-4 sm:grid-cols-2">
          {base.map((f) => field(f.name, t(`field.${f.name}`), f.unit))}
          {extra.map((f) => field(f.name, (lang === "kk" && f.title_kk) || f.title_ru, f.unit))}
        </FieldGroup>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => save.mutate()} disabled={!filled || save.isPending}>
            {save.isPending && <Spinner data-icon="inline-start" />}
            {t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
