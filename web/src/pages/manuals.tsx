import { useMutation, useQueryClient } from "@tanstack/react-query"
import { FileTextIcon, UploadIcon } from "lucide-react"
import { useRef } from "react"
import { toast } from "sonner"

import { PageHeader } from "@/components/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { Spinner } from "@/components/ui/spinner"
import { useI18n, type Key } from "@/i18n"
import { api, ApiError } from "@/lib/api"
import { date } from "@/lib/format"
import { machineTitle, useMachines, useManuals, useProfiles } from "@/lib/queries"
import { useSession } from "@/lib/session"
import type { Machine, Manual } from "@/lib/types"
import { cn } from "@/lib/utils"

const STATUS: Record<Manual["index_status"], { key: Key; tone: string }> = {
  pending: { key: "man.pending", tone: "bg-surface text-muted-foreground" },
  indexing: { key: "man.indexing", tone: "bg-warn-soft text-warn" },
  ready: { key: "man.ready", tone: "bg-ok-soft text-ok" },
  failed: { key: "man.failed", tone: "bg-crit-soft text-crit" },
}
const MAX_MB = 20

function MachineManuals({ machine }: { machine: Machine }) {
  const { t, lang } = useI18n()
  const profiles = useProfiles()
  const client = useQueryClient()
  const manuals = useManuals(machine.id)
  const input = useRef<HTMLInputElement>(null)
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.set("file", file)
      return api<Manual>(`/machines/${machine.id}/manuals`, { method: "POST", body: form })
    },
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["manuals", machine.id] })
      toast.success(t("man.uploaded"))
    },
    onError: (error) => toast.error(error instanceof ApiError && (error.status === 413 || error.status === 415) ? t("man.badFile") : t("common.error")),
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-medium">{machine.name}</CardTitle>
        <CardDescription>{machineTitle(profiles.data, machine.type, lang)}</CardDescription>
        <CardAction>
          <Button variant="outline" size="sm" onClick={() => input.current?.click()} disabled={upload.isPending}>
            {upload.isPending ? <Spinner data-icon="inline-start" /> : <UploadIcon data-icon="inline-start" />}
            {t("man.upload")}
          </Button>
          <input
            ref={input}
            type="file"
            accept="application/pdf"
            className="sr-only"
            onChange={(e) => {
              const file = e.target.files?.[0]
              e.target.value = ""
              if (!file) return
              if (file.size > MAX_MB * 1024 * 1024) return toast.error(t("man.badFile"))
              upload.mutate(file)
            }}
          />
        </CardAction>
      </CardHeader>
      <CardContent>
        {manuals.data?.length ? (
          <ul className="flex flex-col divide-y">
            {manuals.data.map((manual) => {
              const status = STATUS[manual.index_status]
              return (
                <li key={manual.id} className="flex flex-wrap items-center gap-3 py-3 first:pt-0 last:pb-0">
                  <FileTextIcon className="size-4 shrink-0 text-muted-foreground" strokeWidth={1.75} />
                  <div className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate text-sm font-medium">{manual.original_filename}</span>
                    <span className="num text-xs text-muted-foreground">
                      {manual.page_count ? t("man.pages", { n: manual.page_count }) : "—"} · {date(manual.created_at, lang)}
                    </span>
                    {manual.error_message && <span className="text-xs text-muted-foreground text-pretty">{manual.error_message}</span>}
                  </div>
                  <span className={cn("inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium", status.tone)}>
                    {(manual.index_status === "indexing" || manual.index_status === "pending") && <Spinner className="size-3" />}
                    {t(status.key)}
                  </span>
                </li>
              )
            })}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">{manuals.isPending ? "…" : t("man.none")}</p>
        )}
      </CardContent>
    </Card>
  )
}

export function ManualsPage() {
  const { t } = useI18n()
  const { auth } = useSession()
  const machines = useMachines(auth?.workshop.id)
  return (
    <>
      <PageHeader title={t("man.title")} description={t("man.lead")} />
      {machines.data?.length === 0 ? (
        <Empty className="border bg-card shadow-card">
          <EmptyHeader>
            <EmptyTitle>{t("dash.emptyTitle")}</EmptyTitle>
            <EmptyDescription>{t("man.noMachines")}</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {machines.data?.map((machine) => <MachineManuals key={machine.id} machine={machine} />)}
        </div>
      )}
    </>
  )
}
