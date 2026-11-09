import { useQuery } from "@tanstack/react-query"
import { PauseIcon, PlayIcon } from "lucide-react"
import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { useI18n } from "@/i18n"
import { api } from "@/lib/api"
import type { IncidentDetail } from "@/lib/types"

const SPEEDS = [1, 1.5, 2]
const time = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`

// Compact player for the operator's recording. The file URL is loaded on the first press.
export function AudioPlayer({ incidentId }: { incidentId: number }) {
  const { t } = useI18n()
  const audio = useRef<HTMLAudioElement>(null)
  const [wanted, setWanted] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [pos, setPos] = useState(0)
  const [dur, setDur] = useState(0)
  const [speed, setSpeed] = useState(1)
  const detail = useQuery({ queryKey: ["incident", incidentId], enabled: wanted, queryFn: () => api<IncidentDetail>(`/incidents/${incidentId}`) })
  const src = detail.data?.attachments.find((a) => a.kind === "voice" || a.kind === "audio")?.url

  useEffect(() => {
    if (src && wanted && audio.current && audio.current.paused) void audio.current.play().catch(() => setPlaying(false))
  }, [src, wanted])

  const toggle = () => {
    if (!src) return setWanted(true)
    if (audio.current?.paused) void audio.current.play()
    else audio.current?.pause()
  }
  const cycle = () => {
    const next = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length]
    setSpeed(next)
    if (audio.current) audio.current.playbackRate = next
  }

  return (
    <div className="flex items-center gap-3 rounded-full border bg-surface/60 py-1 pr-3 pl-1">
      <Button type="button" size="icon" variant="ghost" className="size-11 rounded-full" onClick={toggle} aria-label={playing ? t("player.pause") : t("player.play")}>
        {wanted && detail.isPending ? <Spinner /> : playing ? <PauseIcon /> : <PlayIcon />}
      </Button>
      <input
        type="range"
        min={0}
        max={dur || 1}
        step={0.1}
        value={pos}
        onChange={(e) => {
          if (audio.current) audio.current.currentTime = Number(e.target.value)
        }}
        aria-label={t("player.seek")}
        className="h-1 flex-1 accent-[var(--primary)]"
      />
      <span className="num w-20 text-right text-xs text-muted-foreground">{time(pos)} / {time(dur)}</span>
      <button type="button" onClick={cycle} className="num h-8 min-w-11 rounded-md text-xs text-muted-foreground hover:text-foreground" aria-label={t("player.speed")}>
        {speed}×
      </button>
      {src && (
        <audio
          ref={audio}
          src={src}
          preload="metadata"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onTimeUpdate={(e) => setPos(e.currentTarget.currentTime)}
          onLoadedMetadata={(e) => setDur(Number.isFinite(e.currentTarget.duration) ? e.currentTarget.duration : 0)}
        />
      )}
      {detail.data && !src && <span className="text-xs text-muted-foreground">{t("player.none")}</span>}
    </div>
  )
}
