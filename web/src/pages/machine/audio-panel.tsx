import { useQuery } from "@tanstack/react-query"
import { AudioLinesIcon } from "lucide-react"
import { Link } from "react-router"

import { Hint } from "@/components/hint"
import { SigmaScale } from "@/components/sigma-scale"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { useI18n } from "@/i18n"
import { api } from "@/lib/api"
import { date } from "@/lib/format"
import type { Incident, IncidentDetail } from "@/lib/types"

// Latest machine-sound check: deviation in σ against the machine's own baseline, and the
// spectrogram the backend drew (left: baseline, right: this recording).
export function AudioPanel({ incidents }: { incidents: Incident[] }) {
  const { t, lang } = useI18n()
  const latest = incidents
    .filter((i) => i.audio_zscore !== null)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
  const detail = useQuery({
    queryKey: ["incident", latest?.id],
    enabled: latest !== undefined,
    queryFn: () => api<IncidentDetail>(`/incidents/${latest!.id}`),
  })
  const spectrogram = detail.data?.attachments.find((a) => a.kind === "spectrogram")
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-1 text-base font-medium">
          {t("audio.title")}
          <Hint text={t("hint.audio")} />
        </CardTitle>
        <CardDescription>{latest ? t("audio.recorded", { date: date(latest.created_at, lang, true) }) : t("audio.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        {!latest ? (
          <Empty className="border border-dashed">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <AudioLinesIcon />
              </EmptyMedia>
              <EmptyTitle>{t("audio.emptyTitle")}</EmptyTitle>
              <EmptyDescription>{t("audio.empty")}</EmptyDescription>
            </EmptyHeader>
            <EmptyContent>
              <Button asChild variant="outline" size="sm">
                <Link to="/app/telegram">{t("tg.open")}</Link>
              </Button>
            </EmptyContent>
          </Empty>
        ) : (
          <>
            <SigmaScale z={latest.audio_zscore ?? 0} />
            {detail.isPending ? (
              <Skeleton className="aspect-[2/1] w-full" />
            ) : spectrogram ? (
              <figure className="flex flex-col gap-2">
                <div className="grid grid-cols-2 text-xs text-muted-foreground">
                  <span>{t("audio.baseline")}</span>
                  <span className="text-right">{t("audio.now")}</span>
                </div>
                <img src={spectrogram.url} alt={t("audio.spectrogramAlt")} loading="lazy" className="w-full rounded-md border bg-white" />
                <figcaption className="text-xs text-muted-foreground">{t("audio.caption")}</figcaption>
              </figure>
            ) : (
              <p className="text-sm text-muted-foreground">{t("audio.noImage")}</p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
