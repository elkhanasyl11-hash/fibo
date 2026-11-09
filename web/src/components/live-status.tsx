import { useEffect, useState } from "react"

import { useI18n } from "@/i18n"

const TICK_MS = 5000

// "Updated 12 s ago": the overview refreshes itself every 15 s; the dot is static (no pulse).
export function LiveStatus({ updatedAt, fetching }: { updatedAt: number; fetching: boolean }) {
  const { t } = useI18n()
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), TICK_MS)
    return () => clearInterval(id)
  }, [])
  const seconds = updatedAt ? Math.max(0, Math.round((now - updatedAt) / 1000)) : null
  return (
    <span className="inline-flex items-center gap-2" aria-live="off">
      <span aria-hidden className={fetching ? "size-1.5 rounded-full bg-warn" : "size-1.5 rounded-full bg-ok"} />
      {seconds === null ? "—" : seconds < 10 ? t("live.now") : t("live.ago", { s: seconds })}
    </span>
  )
}
