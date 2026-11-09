import { FileTextIcon } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { useI18n } from "@/i18n"
import { useManuals } from "@/lib/queries"
import { cn } from "@/lib/utils"

// The machine's PDF manual in the browser's own viewer, opened at ?page= (from an incident card
// or an assistant citation). The browser viewer has its own text search (Ctrl+F).
export function DocsTab({ machineId, initialPage }: { machineId: number; initialPage: number | null }) {
  const { t } = useI18n()
  const manuals = useManuals(machineId)
  const ready = (manuals.data ?? []).filter((m) => m.index_status === "ready" || m.page_count)
  const [selected, setSelected] = useState<number | null>(null)
  const [page, setPage] = useState(initialPage ?? 1)
  const manual = ready.find((m) => m.id === selected) ?? ready[0]

  if (manuals.isPending) return <Skeleton className="h-96 w-full" />
  if (!manual) {
    return (
      <Empty className="border bg-card shadow-card">
        <EmptyHeader>
          <EmptyTitle>{t("docs.emptyTitle")}</EmptyTitle>
          <EmptyDescription>{t("docs.empty")}</EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <Button asChild variant="outline"><Link to="/app/manuals">{t("man.upload")}</Link></Button>
        </EmptyContent>
      </Empty>
    )
  }
  const src = `${manual.url}#page=${page}`
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-medium">{t("docs.title")}</CardTitle>
        <CardDescription>{t("docs.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          {ready.map((m) => (
            <button key={m.id} type="button" onClick={() => setSelected(m.id)} className={cn("inline-flex h-9 items-center gap-2 rounded-full border px-3 text-sm", m.id === manual.id ? "border-primary text-foreground" : "text-muted-foreground")}>
              <FileTextIcon className="size-4" />
              <span className="max-w-48 truncate">{m.original_filename}</span>
            </button>
          ))}
          <form className="ml-auto flex items-center gap-2" onSubmit={(e) => e.preventDefault()}>
            <label htmlFor="pdf-page" className="text-sm text-muted-foreground">{t("docs.page")}</label>
            <Input id="pdf-page" type="number" min={1} max={manual.page_count ?? undefined} value={page} onChange={(e) => setPage(Math.max(1, Number(e.target.value) || 1))} className="num h-9 w-20" />
            <span className="num text-sm text-muted-foreground">/ {manual.page_count ?? "?"}</span>
          </form>
        </div>
        <object key={`${manual.id}-${page}`} data={src} type="application/pdf" className="h-[70svh] w-full rounded-md border bg-white" aria-label={manual.original_filename}>
          <a href={src} target="_blank" rel="noreferrer" className="text-primary underline">{t("docs.open")}</a>
        </object>
      </CardContent>
    </Card>
  )
}
