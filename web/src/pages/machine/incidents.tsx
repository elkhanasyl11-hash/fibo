import { useMutation, useQueryClient } from "@tanstack/react-query"
import { AudioLinesIcon, CameraIcon, CheckIcon, MessageSquareTextIcon, MicIcon } from "lucide-react"
import { toast } from "sonner"

import { LevelBadge } from "@/components/level"
import { SourceBadge } from "@/components/source-badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { useI18n, type Key } from "@/i18n"
import { api } from "@/lib/api"
import { date } from "@/lib/format"
import type { Incident } from "@/lib/types"
import { cn } from "@/lib/utils"

const INPUT = { voice: MicIcon, audio: AudioLinesIcon, photo: CameraIcon, text: MessageSquareTextIcon }
const STATUS: Record<Incident["status"], Key> = {
  received: "inc.status.received",
  processing: "inc.status.processing",
  open: "inc.status.open",
  resolved: "inc.status.resolved",
  failed: "inc.status.failed",
}

export function IncidentList({ incidents }: { incidents: Incident[] }) {
  const { t, lang } = useI18n()
  const client = useQueryClient()
  const resolve = useMutation({
    mutationFn: (id: number) => api(`/incidents/${id}/resolve`, { method: "PATCH" }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["incidents"] })
      client.invalidateQueries({ queryKey: ["machine-summary"] })
      toast.success(t("inc.resolvedToast"))
    },
    onError: () => toast.error(t("common.error")),
  })
  const sorted = [...incidents].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 12)
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-medium">{t("inc.title")}</CardTitle>
        <CardDescription>{t("inc.lead")}</CardDescription>
      </CardHeader>
      <CardContent>
        {sorted.length === 0 ? (
          <Empty className="border border-dashed">
            <EmptyHeader>
              <EmptyTitle>{t("inc.emptyTitle")}</EmptyTitle>
              <EmptyDescription>{t("inc.empty")}</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <ul className="flex flex-col divide-y">
            {sorted.map((incident) => {
              const Icon = INPUT[incident.input_type]
              const active = incident.status === "open"
              return (
                <li key={incident.id} className={cn("flex flex-col gap-3 py-4 first:pt-0 last:pb-0", incident.safety_triggered && active && "rounded-md bg-crit-soft p-3 first:pt-3 last:pb-3")}>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                    <Icon className="size-4 text-muted-foreground" strokeWidth={1.75} />
                    <span className="num text-sm text-muted-foreground">{date(incident.created_at, lang, true)}</span>
                    <LevelBadge level={incident.level} />
                    <span className="text-xs text-muted-foreground">{t(STATUS[incident.status])}</span>
                    {incident.safety_triggered && <span className="text-xs font-medium text-crit">{t("inc.safety")}</span>}
                  </div>
                  {incident.verdict && <p className="text-[15px] text-pretty">{incident.verdict}</p>}
                  {incident.transcript && <p className="text-sm text-muted-foreground text-pretty">«{incident.transcript}»</p>}
                  {incident.causes.length > 0 && (
                    <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
                      {incident.causes.map((cause) => (
                        <li key={String(cause)}>· {String(cause)}</li>
                      ))}
                    </ul>
                  )}
                  {incident.error_message && <p className="text-sm text-destructive">{incident.error_message}</p>}
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-3">
                      <SourceBadge source={incident.ai_source} degraded={incident.degraded} />
                      {incident.manual_pages.length > 0 && (
                        <span className="num text-xs text-muted-foreground">{t("inc.pages", { pages: incident.manual_pages.join(", ") })}</span>
                      )}
                    </div>
                    {active && (
                      <Button variant="outline" size="sm" onClick={() => resolve.mutate(incident.id)} disabled={resolve.isPending}>
                        <CheckIcon data-icon="inline-start" />
                        {t("inc.resolve")}
                      </Button>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
