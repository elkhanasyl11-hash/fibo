import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Trash2Icon } from "lucide-react"
import { useState } from "react"
import { useNavigate, useParams, useSearchParams } from "react-router"
import { toast } from "sonner"

import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardFooter } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSeparator,
  FieldSet,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
  InputGroupText,
} from "@/components/ui/input-group"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { useI18n } from "@/i18n"
import { api, ApiError } from "@/lib/api"
import { useProfiles } from "@/lib/queries"
import { useSession } from "@/lib/session"
import type { Machine } from "@/lib/types"

interface FormValues {
  name: string
  type: string
  model: string
  criticality: string
  cost: string
  repair: string
  lastMaintenance: string
  interval: string
  batch: string
  toolChanged: string
}

const FOOD = new Set(["bakery", "confectionery", "dairy"])
const toDate = (iso: string | null) => (iso ? iso.slice(0, 10) : "")
const toLocal = (iso: string | null) => {
  if (!iso) return ""
  const date = new Date(iso)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16)
}

function surveyNumber(
  answers: { question_id: string; answer: unknown }[] | undefined,
  id: string
): string {
  const found = answers?.find((a) => a.question_id === id)?.answer
  return typeof found === "number" && Number.isFinite(found)
    ? String(found)
    : ""
}

function fromMachine(m: Machine): FormValues {
  return {
    name: m.name,
    type: m.type,
    model: m.model ?? "",
    criticality: String(m.criticality),
    cost: String(Number(m.downtime_cost_per_hour_kzt)),
    repair: String(m.avg_repair_hours),
    lastMaintenance: toDate(m.last_maintenance_at),
    interval: m.maintenance_interval_hours
      ? String(m.maintenance_interval_hours)
      : "",
    batch: m.batch_value_kzt ? String(Number(m.batch_value_kzt)) : "",
    toolChanged: toLocal(m.tool_changed_at),
  }
}

export function MachineFormPage() {
  const { id } = useParams()
  const existing = useQuery({
    queryKey: ["machine", id],
    enabled: id !== undefined,
    queryFn: () => api<Machine>(`/machines/${id}`),
  })
  if (id !== undefined && !existing.data) {
    return existing.isError ? null : <Spinner />
  }
  return (
    <MachineForm
      key={id ?? "new"}
      id={id}
      initial={existing.data ? fromMachine(existing.data) : undefined}
    />
  )
}

function MachineForm({
  id,
  initial,
}: {
  id: string | undefined
  initial: FormValues | undefined
}) {
  const editing = id !== undefined
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const client = useQueryClient()
  const { t, lang } = useI18n()
  const { auth } = useSession()
  const profiles = useProfiles()
  const profileId = auth?.workshop.profile
  const profile = profiles.data?.find((p) => p.id === profileId)
  const answers = auth?.workshop.survey?.answers
  const [values, setValues] = useState<FormValues>(
    initial ?? {
      name: "",
      type: "",
      model: "",
      criticality: "2",
      cost: params.get("cost") ?? surveyNumber(answers, "downtime_cost"),
      repair: "4",
      lastMaintenance: "",
      interval: "",
      batch: surveyNumber(answers, "batch_value"),
      toolChanged: "",
    }
  )
  const [submitted, setSubmitted] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const set = (patch: Partial<FormValues>) =>
    setValues((v) => ({ ...v, ...patch }))
  const errors = {
    name: !values.name.trim(),
    type: !editing && !values.type,
    cost:
      values.cost.trim() === "" ||
      !Number.isFinite(Number(values.cost)) ||
      Number(values.cost) < 0,
    repair: !(Number(values.repair) > 0 && Number(values.repair) <= 720),
  }
  const invalid = Object.values(errors).some(Boolean)

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        name: values.name.trim(),
        model: values.model.trim() || null,
        criticality: Number(values.criticality),
        downtime_cost_per_hour_kzt: values.cost,
        avg_repair_hours: Number(values.repair),
        last_maintenance_at: values.lastMaintenance
          ? new Date(`${values.lastMaintenance}T09:00:00`).toISOString()
          : null,
        maintenance_interval_hours: values.interval
          ? Number(values.interval)
          : null,
        batch_value_kzt: values.batch || null,
        tool_changed_at: values.toolChanged
          ? new Date(values.toolChanged).toISOString()
          : null,
      }
      const machine = editing
        ? await api<Machine>(`/machines/${id}`, { method: "PATCH", json: body })
        : await api<Machine>("/machines", {
            method: "POST",
            json: {
              ...body,
              type: values.type,
              workshop_id: auth?.workshop.id,
            },
          })
      await api("/risk-scores/recompute", {
        method: "POST",
        json: { machine_id: machine.id },
      }).catch(() => undefined)
      return machine
    },
    onSuccess: (machine) => {
      client.invalidateQueries()
      toast.success(editing ? t("form.updated") : t("form.created"))
      navigate(`/app/machines/${machine.id}`)
    },
    onError: (error) =>
      toast.error(
        error instanceof ApiError && error.status === 422
          ? t("form.invalid")
          : t("common.error")
      ),
  })
  const remove = useMutation({
    mutationFn: () => api(`/machines/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      client.invalidateQueries()
      navigate("/app/machines")
    },
    onError: () => toast.error(t("common.error")),
  })

  const money = (
    key: "cost" | "batch",
    label: string,
    help: string,
    invalidText?: string
  ) => (
    <Field
      data-invalid={
        submitted && key === "cost" && errors.cost ? true : undefined
      }
    >
      <FieldLabel htmlFor={key}>{label}</FieldLabel>
      <InputGroup>
        <InputGroupInput
          id={key}
          type="number"
          inputMode="numeric"
          min={0}
          className="num"
          value={values[key]}
          onChange={(e) => set({ [key]: e.target.value })}
        />
        <InputGroupAddon align="inline-end">
          <InputGroupText>₸</InputGroupText>
        </InputGroupAddon>
      </InputGroup>
      {submitted && key === "cost" && errors.cost && invalidText ? (
        <FieldError>{invalidText}</FieldError>
      ) : (
        <FieldDescription>{help}</FieldDescription>
      )}
    </Field>
  )

  return (
    <>
      <PageHeader
        title={editing ? t("form.editTitle") : t("form.newTitle")}
        description={t("form.lead")}
      />
      <Card className="max-w-3xl">
        <CardContent>
          <form
            id="machine"
            onSubmit={(e) => {
              e.preventDefault()
              setSubmitted(true)
              if (!invalid) save.mutate()
            }}
          >
            <FieldGroup>
              <div className="grid gap-6 sm:grid-cols-2">
                <Field
                  data-invalid={submitted && errors.name ? true : undefined}
                >
                  <FieldLabel htmlFor="name">{t("form.name")}</FieldLabel>
                  <Input
                    id="name"
                    maxLength={100}
                    placeholder={t("form.namePh")}
                    value={values.name}
                    aria-invalid={submitted && errors.name ? true : undefined}
                    onChange={(e) => set({ name: e.target.value })}
                  />
                  {submitted && errors.name && (
                    <FieldError>{t("acc.required")}</FieldError>
                  )}
                </Field>
                <Field
                  data-invalid={submitted && errors.type ? true : undefined}
                >
                  <FieldLabel htmlFor="type">{t("form.type")}</FieldLabel>
                  <Select
                    value={values.type}
                    disabled={editing}
                    onValueChange={(type) => {
                      const entry = profile?.equipment_catalog.find(
                        (e) => e.type === type
                      )
                      set({
                        type,
                        criticality: entry
                          ? String(entry.default_criticality)
                          : values.criticality,
                      })
                    }}
                  >
                    <SelectTrigger
                      id="type"
                      className="w-full"
                      aria-invalid={submitted && errors.type ? true : undefined}
                    >
                      <SelectValue placeholder={t("form.typePh")} />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectGroup>
                        {profile?.equipment_catalog.map((entry) => (
                          <SelectItem key={entry.type} value={entry.type}>
                            {(lang === "kk" && entry.title_kk) ||
                              entry.title_ru}
                          </SelectItem>
                        ))}
                      </SelectGroup>
                    </SelectContent>
                  </Select>
                  {submitted && errors.type && (
                    <FieldError>{t("acc.required")}</FieldError>
                  )}
                </Field>
              </div>
              <Field>
                <FieldLabel htmlFor="model">{t("form.model")}</FieldLabel>
                <Input
                  id="model"
                  maxLength={100}
                  placeholder={t("form.modelPh")}
                  value={values.model}
                  onChange={(e) => set({ model: e.target.value })}
                />
              </Field>
              <FieldSet>
                <FieldLegend variant="label">
                  {t("form.criticality")}
                </FieldLegend>
                <FieldDescription>{t("form.criticalityHelp")}</FieldDescription>
                <ToggleGroup
                  type="single"
                  variant="outline"
                  value={values.criticality}
                  onValueChange={(v) => v && set({ criticality: v })}
                  className="w-full"
                >
                  {(["1", "2", "3"] as const).map((level) => (
                    <ToggleGroupItem
                      key={level}
                      value={level}
                      className="flex-1"
                    >
                      {t(`crit.${level}`)}
                    </ToggleGroupItem>
                  ))}
                </ToggleGroup>
              </FieldSet>
              <FieldSeparator />
              <div className="grid gap-6 sm:grid-cols-2">
                {money(
                  "cost",
                  t("form.cost"),
                  t("form.costHelp"),
                  t("form.costError")
                )}
                <Field
                  data-invalid={submitted && errors.repair ? true : undefined}
                >
                  <FieldLabel htmlFor="repair">{t("form.repair")}</FieldLabel>
                  <InputGroup>
                    <InputGroupInput
                      id="repair"
                      type="number"
                      inputMode="decimal"
                      min={0.5}
                      max={720}
                      step={0.5}
                      className="num"
                      value={values.repair}
                      onChange={(e) => set({ repair: e.target.value })}
                    />
                    <InputGroupAddon align="inline-end">
                      <InputGroupText>{t("unit.h")}</InputGroupText>
                    </InputGroupAddon>
                  </InputGroup>
                  <FieldDescription>{t("form.repairHelp")}</FieldDescription>
                </Field>
                {profileId &&
                  FOOD.has(profileId) &&
                  money("batch", t("form.batch"), t("form.batchHelp"))}
              </div>
              <FieldSeparator />
              <div className="grid gap-6 sm:grid-cols-2">
                <Field>
                  <FieldLabel htmlFor="last">
                    {t("form.lastMaintenance")}
                  </FieldLabel>
                  <Input
                    id="last"
                    type="date"
                    className="num"
                    max={new Date().toISOString().slice(0, 10)}
                    value={values.lastMaintenance}
                    onChange={(e) => set({ lastMaintenance: e.target.value })}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="interval">
                    {t("form.interval")}
                  </FieldLabel>
                  <InputGroup>
                    <InputGroupInput
                      id="interval"
                      type="number"
                      inputMode="numeric"
                      min={1}
                      className="num"
                      value={values.interval}
                      onChange={(e) => set({ interval: e.target.value })}
                    />
                    <InputGroupAddon align="inline-end">
                      <InputGroupText>{t("unit.h")}</InputGroupText>
                    </InputGroupAddon>
                  </InputGroup>
                  <FieldDescription>{t("form.intervalHelp")}</FieldDescription>
                </Field>
                {profileId === "metalworking" && (
                  <Field>
                    <FieldLabel htmlFor="tool">
                      {t("form.toolChanged")}
                    </FieldLabel>
                    <Input
                      id="tool"
                      type="datetime-local"
                      className="num"
                      value={values.toolChanged}
                      onChange={(e) => set({ toolChanged: e.target.value })}
                    />
                    <FieldDescription>{t("form.toolHelp")}</FieldDescription>
                  </Field>
                )}
              </div>
            </FieldGroup>
          </form>
        </CardContent>
        <CardFooter className="justify-between gap-3">
          {editing ? (
            <Button
              variant="ghost"
              className="text-destructive"
              onClick={() => setConfirmDelete(true)}
            >
              <Trash2Icon data-icon="inline-start" />
              {t("common.delete")}
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => navigate(-1)}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" form="machine" disabled={save.isPending}>
              {save.isPending && <Spinner data-icon="inline-start" />}
              {editing ? t("common.save") : t("form.create")}
            </Button>
          </div>
        </CardFooter>
      </Card>
      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t("form.deleteTitle", { name: values.name })}
            </DialogTitle>
            <DialogDescription>{t("form.deleteBody")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
            >
              {t("common.delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
