import { useI18n } from "@/i18n"
import { levelVar } from "@/lib/levels"
import type { Level } from "@/lib/types"
import { cn } from "@/lib/utils"

export function LevelDot({ level, className }: { level: Level | null; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("inline-block size-2 shrink-0 rounded-full", className)}
      style={{ background: level ? levelVar[level] : "var(--muted-foreground)" }}
    />
  )
}

const tone: Record<Level, string> = {
  normal: "bg-ok-soft text-ok",
  warning: "bg-warn-soft text-warn",
  critical: "bg-crit-soft text-crit",
}

export function LevelBadge({ level, className }: { level: Level | null; className?: string }) {
  const { t } = useI18n()
  if (!level) {
    return <span className={cn("text-xs text-muted-foreground", className)}>{t("level.none")}</span>
  }
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium whitespace-nowrap",
        tone[level],
        className
      )}
    >
      <LevelDot level={level} />
      {t(`level.${level}`)}
    </span>
  )
}
