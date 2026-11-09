import { useI18n, type Key } from "@/i18n"
import { cn } from "@/lib/utils"

const DEGRADED: Record<string, Key> = {
  ai_sidecar_unavailable: "degraded.ai_sidecar_unavailable",
  ai_unavailable: "degraded.ai_unavailable",
  ai_mode_mock: "degraded.ai_mode_mock",
  ai_manual_not_indexed: "degraded.ai_manual_not_indexed",
  ai_baseline_mismatch: "degraded.ai_baseline_mismatch",
  ai_baseline_missing: "degraded.ai_baseline_missing",
  ai_baseline_rebuilt: "degraded.ai_baseline_rebuilt",
  ai_contract_mismatch: "degraded.ai_contract_mismatch",
  ai_auth_failed: "degraded.ai_auth_failed",
  no_description: "degraded.no_description",
}

// "AI" or "built-in modules", plus why the answer is degraded, in plain words.
export function SourceBadge({
  source,
  degraded = [],
  className,
}: {
  source: "ai" | "builtin" | null
  degraded?: string[]
  className?: string
}) {
  const { t } = useI18n()
  if (!source) return null
  const notes = degraded.filter((code) => code !== "ai_mode_mock" || source === "builtin")
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-x-2 gap-y-1 text-xs", className)}>
      <span
        className={cn(
          "inline-flex h-6 items-center gap-1.5 rounded-full border px-2.5 font-medium",
          source === "ai" ? "border-primary/25 text-primary" : "border-border text-muted-foreground"
        )}
      >
        <span aria-hidden className={cn("size-1.5 rounded-full", source === "ai" ? "bg-primary" : "bg-muted-foreground")} />
        {source === "ai" ? t("source.ai") : t("source.builtin")}
      </span>
      {notes.map((code) => (
        <span key={code} className="text-muted-foreground">
          {DEGRADED[code] ? t(DEGRADED[code]) : code}
        </span>
      ))}
    </span>
  )
}
