import { useMutation, useQueryClient } from "@tanstack/react-query"
import { CameraIcon, CheckIcon, ImageUpIcon, XIcon } from "lucide-react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"
import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router"
import { toast } from "sonner"

import { PageHeader } from "@/components/page-header"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Spinner } from "@/components/ui/spinner"
import { useI18n, type Key } from "@/i18n"
import { api, ApiError } from "@/lib/api"
import { num } from "@/lib/format"
import { motionTokens, springs } from "@/lib/motion"
import { useMachines, useProfiles } from "@/lib/queries"
import { useSession } from "@/lib/session"
import type { PanelResult, ProfileConfig } from "@/lib/types"
import { cn } from "@/lib/utils"

const BASE_FIELDS = new Set(["spindle_rpm", "load_pct", "temperature_c", "operating_hours"])

function fieldTitle(field: string, profile: ProfileConfig | undefined, lang: "ru" | "kk", t: (k: Key) => string): string {
  if (BASE_FIELDS.has(field)) return t(`field.${field}` as Key)
  const extra = profile?.extra_fields.find((f) => f.name === field)
  return extra ? (lang === "kk" && extra.title_kk) || extra.title_ru : field
}

function reasonText(reason: string, t: (k: Key, v?: Record<string, string>) => string): string {
  const range = reason.match(/^outside valid range (.+)$/)
  if (range) return t("panel.reason.range", { range: range[1].replace("..", "–") })
  if (reason === "not readable") return t("panel.reason.unreadable")
  if (reason === "field not used by this profile") return t("panel.reason.unknown")
  return reason
}

export function PanelPhotoPage({ embedded = false }: { embedded?: boolean }) {
  const { t, lang } = useI18n()
  const reduce = useReducedMotion()
  const client = useQueryClient()
  const { auth } = useSession()
  const machines = useMachines(auth?.workshop.id)
  const profiles = useProfiles()
  const profile = profiles.data?.find((p) => p.id === auth?.workshop.profile)
  const [machineId, setMachineId] = useState<string>("")
  const [file, setFile] = useState<File | null>(null)
  const [edited, setEdited] = useState<Record<string, string>>({})

  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file])
  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview)
  }, [preview])

  const read = useMutation({
    mutationFn: () => {
      const form = new FormData()
      form.set("machine_id", machineId)
      form.set("file", file as File)
      return api<PanelResult>("/readings/panel-photo", { method: "POST", body: form })
    },
    onSuccess: (data) => setEdited(Object.fromEntries(data.values.map((v) => [v.field, v.value === null ? "" : String(v.value)]))),
  })
  const save = useMutation({
    mutationFn: async () => {
      const result = read.data as PanelResult
      const values = Object.fromEntries(Object.entries(edited).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)]))
      const base = Object.fromEntries(Object.entries(values).filter(([k]) => BASE_FIELDS.has(k)))
      const extra = Object.fromEntries(Object.entries(values).filter(([k]) => result.extra_fields.includes(k)))
      await api("/readings", {
        method: "POST",
        json: { machine_id: result.machine_id, source: "panel", ...base, ...(Object.keys(extra).length ? { extra } : {}) },
      })
      await api("/risk-scores/recompute", { method: "POST", json: { machine_id: result.machine_id } })
    },
    onSuccess: () => {
      client.invalidateQueries()
      toast.success(t("panel.saved"))
      setFile(null)
      read.reset()
      setEdited({})
    },
    onError: (error) => toast.error(error instanceof ApiError && error.status === 422 ? t("reading.invalid") : t("common.error")),
  })

  const readError = read.error instanceof ApiError ? (read.error.status === 422 ? read.error.message.replace(/^Photo is not usable: /, "") : t("common.error")) : null
  const result = read.data

  return (
    <>
      {!embedded && <PageHeader title={t("panel.title")} description={t("panel.lead")} />}
      <Alert>
        <CameraIcon />
        <AlertTitle>{t("panel.tgTitle")}</AlertTitle>
        <AlertDescription>
          <span>
            {t("panel.tgBody")}{" "}
            <Link to="/app/telegram" className="text-primary underline-offset-4 hover:underline">
              {t("tg.open")}
            </Link>
          </span>
        </AlertDescription>
      </Alert>
      <div className="grid gap-4 lg:grid-cols-[1fr_1.1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-medium">{t("panel.step1")}</CardTitle>
            <CardDescription>{t("panel.step1Lead")}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            <Field>
              <FieldLabel htmlFor="panel-machine">{t("table.machine")}</FieldLabel>
              <Select value={machineId} onValueChange={setMachineId}>
                <SelectTrigger id="panel-machine" className="w-full">
                  <SelectValue placeholder={t("panel.pickMachine")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {machines.data?.map((m) => (
                      <SelectItem key={m.id} value={String(m.id)}>
                        {m.name}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </Field>
            <label
              className={cn(
                "relative flex aspect-[4/3] cursor-pointer flex-col items-center justify-center gap-3 overflow-hidden rounded-lg border border-dashed bg-surface text-sm text-muted-foreground transition-colors hover:border-foreground/30",
                preview && "border-solid"
              )}
            >
              {preview ? (
                <img src={preview} alt={t("panel.previewAlt")} className="absolute inset-0 size-full object-contain" />
              ) : (
                <>
                  <ImageUpIcon className="size-6" strokeWidth={1.5} />
                  <span>{t("panel.drop")}</span>
                </>
              )}
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                capture="environment"
                className="sr-only"
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null)
                  read.reset()
                }}
              />
            </label>
            {readError && <p role="alert" className="text-sm text-destructive">{readError}</p>}
          </CardContent>
          <CardFooter className="justify-end gap-2">
            {file && (
              <Button variant="ghost" onClick={() => { setFile(null); read.reset() }}>
                <XIcon data-icon="inline-start" />
                {t("common.cancel")}
              </Button>
            )}
            <Button onClick={() => read.mutate()} disabled={!file || !machineId || read.isPending}>
              {read.isPending && <Spinner data-icon="inline-start" />}
              {t("panel.read")}
            </Button>
          </CardFooter>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base font-medium">{t("panel.step2")}</CardTitle>
            <CardDescription>{t("panel.step2Lead")}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-5">
            {!result ? (
              <p className="text-sm text-muted-foreground">{read.isPending ? t("panel.reading") : t("panel.waiting")}</p>
            ) : (
              <AnimatePresence>
                <motion.div key="result" className="flex flex-col gap-5" initial={{ opacity: 0, y: reduce ? 0 : motionTokens.distance.sm }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={springs.gentle}>
                  {result.values.length === 0 && <p className="text-sm text-muted-foreground">{t("panel.nothing")}</p>}
                  <ul className="flex flex-col gap-4">
                    {result.values.map((value) => (
                      <li key={value.field} className="grid grid-cols-[1fr_120px] items-center gap-3">
                        <div className="flex min-w-0 flex-col gap-1.5">
                          <label htmlFor={`pv-${value.field}`} className="truncate text-sm">
                            {fieldTitle(value.field, profile, lang, t)}
                          </label>
                          <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <div className="h-1 w-20 rounded-full bg-surface">
                              <div className="h-full rounded-full bg-foreground/50" style={{ width: `${value.confidence * 100}%` }} />
                            </div>
                            <span className="num">{t("panel.confidence", { v: num(value.confidence * 100) })}</span>
                            {value.raw_text && <span className="truncate">«{value.raw_text}»</span>}
                          </div>
                        </div>
                        <Input
                          id={`pv-${value.field}`}
                          type="number"
                          inputMode="decimal"
                          className="num"
                          value={edited[value.field] ?? ""}
                          onChange={(e) => setEdited((v) => ({ ...v, [value.field]: e.target.value }))}
                        />
                      </li>
                    ))}
                  </ul>
                  {result.rejected.length > 0 && (
                    <section className="flex flex-col gap-2 rounded-md bg-surface p-3">
                      <h3 className="text-sm font-medium">{t("panel.rejected")}</h3>
                      <ul className="flex flex-col gap-1.5 text-sm text-muted-foreground">
                        {result.rejected.map((r) => (
                          <li key={`${r.field}-${r.raw_text}`} className="flex flex-wrap gap-x-2">
                            <span className="text-foreground">{fieldTitle(r.field, profile, lang, t)}</span>
                            {r.value !== null && <span className="num">{num(r.value, 1, lang)}</span>}
                            <span>· {reasonText(r.reason, t)}</span>
                          </li>
                        ))}
                      </ul>
                    </section>
                  )}
                </motion.div>
              </AnimatePresence>
            )}
          </CardContent>
          {result && result.values.length > 0 && (
            <CardFooter className="justify-end">
              <Button onClick={() => save.mutate()} disabled={save.isPending}>
                {save.isPending ? <Spinner data-icon="inline-start" /> : <CheckIcon data-icon="inline-start" />}
                {t("panel.confirm")}
              </Button>
            </CardFooter>
          )}
        </Card>
      </div>
    </>
  )
}
