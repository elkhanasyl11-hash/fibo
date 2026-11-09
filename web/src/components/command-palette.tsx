import { Command } from "cmdk"
import {
  BookOpenIcon,
  CpuIcon,
  FileBarChartIcon,
  GaugeIcon,
  MessageSquareTextIcon,
  PlusIcon,
  SearchIcon,
  SirenIcon,
  SlidersHorizontalIcon,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useNavigate } from "react-router"

import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import { Kbd } from "@/components/ui/kbd"
import { useI18n, type Key } from "@/i18n"
import { useMachines } from "@/lib/queries"
import { useSession } from "@/lib/session"

const SCREENS: { to: string; label: Key; icon: typeof GaugeIcon }[] = [
  { to: "/app", label: "nav.risk", icon: GaugeIcon },
  { to: "/app/machines", label: "nav.machines", icon: CpuIcon },
  { to: "/app/input", label: "nav.input", icon: SlidersHorizontalIcon },
  { to: "/app/incidents", label: "nav.incidents", icon: SirenIcon },
  { to: "/app/chat", label: "nav.chat", icon: MessageSquareTextIcon },
  { to: "/app/reports", label: "nav.reports", icon: FileBarChartIcon },
  { to: "/app/manuals", label: "nav.manuals", icon: BookOpenIcon },
]

const itemClass =
  "flex h-11 cursor-pointer items-center gap-3 rounded-md px-3 text-sm text-foreground data-[selected=true]:bg-accent [&_svg]:size-4 [&_svg]:text-muted-foreground"

// ⌘K / Ctrl+K: jump to any screen or machine.
export function CommandPalette() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const { auth } = useSession()
  const machines = useMachines(auth?.workshop.id)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        setOpen((o) => !o)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const go = (to: string) => {
    setOpen(false)
    navigate(to)
  }

  return (
    <>
      <Button
        variant="outline"
        className="h-9 w-9 justify-center gap-2 px-0 text-muted-foreground sm:w-56 sm:justify-start sm:px-3"
        onClick={() => setOpen(true)}
        aria-label={t("cmd.open")}
      >
        <SearchIcon data-icon="inline-start" />
        <span className="hidden flex-1 text-left sm:inline">{t("cmd.placeholder")}</span>
        <Kbd className="hidden sm:inline-flex">⌘K</Kbd>
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="overflow-hidden p-0 sm:max-w-lg" showCloseButton={false}>
          <DialogTitle className="sr-only">{t("cmd.open")}</DialogTitle>
          <DialogDescription className="sr-only">{t("cmd.placeholder")}</DialogDescription>
          <Command loop className="flex flex-col">
            <div className="flex items-center gap-2 border-b px-3">
              <SearchIcon className="size-4 text-muted-foreground" />
              <Command.Input autoFocus placeholder={t("cmd.placeholder")} className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground" />
            </div>
            <Command.List className="max-h-80 overflow-y-auto p-2">
              <Command.Empty className="px-3 py-6 text-center text-sm text-muted-foreground">{t("cmd.empty")}</Command.Empty>
              <Command.Group heading={t("cmd.screens")} className="text-xs text-muted-foreground [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5">
                {SCREENS.map(({ to, label, icon: Icon }) => (
                  <Command.Item key={to} value={t(label)} onSelect={() => go(to)} className={itemClass}>
                    <Icon />
                    {t(label)}
                  </Command.Item>
                ))}
                <Command.Item value={t("machines.add")} onSelect={() => go("/app/machines/new")} className={itemClass}>
                  <PlusIcon />
                  {t("machines.add")}
                </Command.Item>
              </Command.Group>
              {(machines.data?.length ?? 0) > 0 && (
                <Command.Group heading={t("nav.machines")} className="mt-2 text-xs text-muted-foreground [&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5">
                  {machines.data?.map((m) => (
                    <Command.Item key={m.id} value={`${m.name} ${m.model ?? ""} ${m.id}`} onSelect={() => go(`/app/machines/${m.id}`)} className={itemClass}>
                      <CpuIcon />
                      {m.name}
                      {m.model && <span className="text-xs text-muted-foreground">{m.model}</span>}
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
            </Command.List>
          </Command>
        </DialogContent>
      </Dialog>
    </>
  )
}
