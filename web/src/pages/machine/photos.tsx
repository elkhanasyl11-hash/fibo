import { useQuery } from "@tanstack/react-query"
import { ImageIcon } from "lucide-react"
import { useState } from "react"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"
import { Skeleton } from "@/components/ui/skeleton"
import { useI18n } from "@/i18n"
import { api } from "@/lib/api"
import { date } from "@/lib/format"
import type { Incident, IncidentDetail } from "@/lib/types"

interface Baseline {
  id: number
  kind: "audio" | "photo"
  url: string
  created_at: string
}

// Before / after: the reference photo under the latest tool photo, with a draggable divider.
function Compare({ before, after, alt }: { before: string; after: string; alt: string }) {
  const { t } = useI18n()
  const [split, setSplit] = useState(50)
  return (
    <div className="flex flex-col gap-2">
      <div className="relative aspect-[4/3] w-full overflow-hidden rounded-lg border bg-black select-none">
        <img src={after} alt={alt} className="absolute inset-0 size-full object-contain" draggable={false} />
        <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}>
          <img src={before} alt={t("photo.reference")} className="absolute inset-0 size-full object-contain" draggable={false} />
        </div>
        <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-white/90" style={{ left: `${split}%` }} />
        <span className="absolute top-2 left-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white">{t("photo.reference")}</span>
        <span className="absolute top-2 right-2 rounded bg-black/60 px-2 py-0.5 text-xs text-white">{t("photo.current")}</span>
        <input
          type="range"
          min={0}
          max={100}
          value={split}
          onChange={(e) => setSplit(Number(e.target.value))}
          aria-label={t("photo.divider")}
          className="absolute inset-0 size-full cursor-ew-resize opacity-0"
        />
      </div>
    </div>
  )
}

export function PhotosTab({ machineId, incidents }: { machineId: number; incidents: Incident[] }) {
  const { t, lang } = useI18n()
  const baselines = useQuery({ queryKey: ["baselines", machineId], queryFn: () => api<Baseline[]>(`/machines/${machineId}/baselines`) })
  const photoIncidents = incidents.filter((i) => i.input_type === "photo").sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 8)
  const details = useQuery({
    queryKey: ["photo-incidents", machineId, photoIncidents.map((i) => i.id).join(",")],
    enabled: photoIncidents.length > 0,
    queryFn: () => Promise.all(photoIncidents.map((i) => api<IncidentDetail>(`/incidents/${i.id}`))),
  })
  const references = (baselines.data ?? []).filter((b) => b.kind === "photo")
  const current = (details.data ?? []).flatMap((d) => d.attachments.filter((a) => a.kind === "photo").map((a) => ({ ...a, incident: d })))
  const loading = baselines.isPending || (photoIncidents.length > 0 && details.isPending)

  if (loading) return <Skeleton className="h-72 w-full" />
  if (references.length === 0 && current.length === 0) {
    return (
      <Empty className="border bg-card shadow-card">
        <EmptyHeader>
          <EmptyMedia variant="icon"><ImageIcon /></EmptyMedia>
          <EmptyTitle>{t("photo.emptyTitle")}</EmptyTitle>
          <EmptyDescription>{t("photo.empty")}</EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }
  return (
    <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium">{t("photo.compareTitle")}</CardTitle>
          <CardDescription>{t("photo.compareLead")}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {references[0] && current[0] ? (
            <Compare before={references.at(-1)!.url} after={current[0].url} alt={t("photo.current")} />
          ) : (
            <p className="text-sm text-muted-foreground">{t("photo.needBoth")}</p>
          )}
          <p className="text-xs text-muted-foreground">{t("photo.heatmapNote")}</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium">{t("photo.galleryTitle")}</CardTitle>
          <CardDescription>{t("photo.galleryLead")}</CardDescription>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3">
          {references.map((b) => (
            <figure key={`b${b.id}`} className="flex flex-col gap-1">
              <img src={b.url} alt={t("photo.reference")} loading="lazy" className="aspect-[4/3] w-full rounded-md border object-cover" />
              <figcaption className="text-xs text-muted-foreground">{t("photo.reference")} · {date(b.created_at, lang)}</figcaption>
            </figure>
          ))}
          {current.map((a) => (
            <figure key={`a${a.id}`} className="flex flex-col gap-1">
              <img src={a.url} alt={a.incident.verdict ?? t("photo.current")} loading="lazy" className="aspect-[4/3] w-full rounded-md border object-cover" />
              <figcaption className="line-clamp-2 text-xs text-muted-foreground">{date(a.created_at, lang, true)} · {a.incident.verdict ?? "—"}</figcaption>
            </figure>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
