import type { ReactNode } from "react"

export function PageHeader({
  title,
  description,
  actions,
  meta,
}: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  meta?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex min-w-0 flex-col gap-2">
        {meta && <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">{meta}</div>}
        <h1 className="display text-[28px] leading-tight text-balance sm:text-[32px]">{title}</h1>
        {description && <p className="max-w-2xl text-[15px] text-muted-foreground text-pretty">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
