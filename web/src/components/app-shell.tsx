import {
  BellIcon,
  BookOpenIcon,
  CpuIcon,
  FileBarChartIcon,
  GaugeIcon,
  LogOutIcon,
  MessageSquareTextIcon,
  SendIcon,
  SigmaIcon,
  SirenIcon,
  SlidersHorizontalIcon,
} from "lucide-react"
import { useEffect } from "react"
import { Link, NavLink, Outlet, useLocation } from "react-router"

import { Brand, BrandMark } from "@/components/brand"
import { CommandPalette } from "@/components/command-palette"
import { CriticalWatcher } from "@/components/critical-watcher"
import { LangToggle, ThemeToggle } from "@/components/toggles"
import { Button } from "@/components/ui/button"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarRail,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar"
import { useI18n, type Key } from "@/i18n"
import { useIncidents } from "@/lib/queries"
import { useSession } from "@/lib/session"
import { cn } from "@/lib/utils"
import { INDUSTRIES } from "@/pages/onboarding/industries"

type Item = { to: string; label: Key; icon: typeof GaugeIcon; end?: boolean }

const MAIN: Item[] = [
  { to: "/app", label: "nav.risk", icon: GaugeIcon, end: true },
  { to: "/app/machines", label: "nav.machines", icon: CpuIcon },
  { to: "/app/input", label: "nav.input", icon: SlidersHorizontalIcon },
  { to: "/app/incidents", label: "nav.incidents", icon: SirenIcon },
  { to: "/app/chat", label: "nav.chat", icon: MessageSquareTextIcon },
  { to: "/app/reports", label: "nav.reports", icon: FileBarChartIcon },
]
const MORE: Item[] = [
  { to: "/app/manuals", label: "nav.manuals", icon: BookOpenIcon },
  { to: "/app/telegram", label: "nav.telegram", icon: SendIcon },
  { to: "/app/models", label: "nav.models", icon: SigmaIcon },
]
const BOTTOM = MAIN.slice(0, 5)

const isActive = (pathname: string, item: Item) =>
  item.end ? pathname === item.to : pathname.startsWith(item.to)

function NavGroup({ title, items }: { title: Key; items: Item[] }) {
  const { t } = useI18n()
  const { pathname } = useLocation()
  const { setOpenMobile } = useSidebar()
  return (
    <SidebarGroup>
      <SidebarGroupLabel>{t(title)}</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => (
            <SidebarMenuItem key={item.to}>
              <SidebarMenuButton
                asChild
                isActive={isActive(pathname, item)}
                tooltip={t(item.label)}
                className="h-10"
              >
                <NavLink
                  to={item.to}
                  end={item.end}
                  onClick={() => setOpenMobile(false)}
                >
                  <item.icon strokeWidth={1.75} />
                  <span>{t(item.label)}</span>
                </NavLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}

function CriticalBell() {
  const { auth } = useSession()
  const { t } = useI18n()
  const open = useIncidents({
    workshop_id: auth?.workshop.id,
    status: "open",
    limit: 100,
  })
  const urgent = (open.data ?? []).filter(
    (i) => i.safety_triggered || i.level === "critical"
  ).length
  return (
    <Button
      asChild
      variant="ghost"
      size="icon"
      className="relative"
      aria-label={t("top.bell", { n: urgent })}
    >
      <Link to="/app/incidents?status=open">
        <BellIcon />
        {urgent > 0 && (
          <span className="num absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-alert px-1 text-[10px] font-semibold text-white">
            {urgent}
          </span>
        )}
      </Link>
    </Button>
  )
}

function TopBar() {
  const { auth, signOut } = useSession()
  const { t, lang } = useI18n()
  const industry = INDUSTRIES.find((i) => i.id === auth?.workshop.profile)
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/85 px-3 backdrop-blur sm:px-4">
      <SidebarTrigger
        className="hidden md:inline-flex"
        aria-label={t("nav.menu")}
      />
      <Link to="/app" className="md:hidden" aria-label="Fibo">
        <BrandMark />
      </Link>
      <div className="flex min-w-0 flex-col leading-tight">
        <span className="truncate text-sm font-medium">
          {auth?.workshop.name}
        </span>
        {industry && (
          <span className="flex items-center gap-1 truncate text-xs text-muted-foreground">
            <industry.icon className="size-3" />
            {lang === "kk" ? industry.kk : industry.ru}
          </span>
        )}
      </div>
      <div className="ml-auto flex items-center gap-1 sm:gap-2">
        <CommandPalette />
        <CriticalBell />
        <div className="hidden sm:block">
          <LangToggle />
        </div>
        <ThemeToggle />
        <Button
          variant="ghost"
          size="icon"
          className="inline-flex"
          aria-label={t("auth.signOut")}
          onClick={signOut}
        >
          <LogOutIcon />
        </Button>
      </div>
    </header>
  )
}

// Phones (<768 px): the main sections as a bottom bar, 56 px tall targets for gloved hands.
function BottomNav() {
  const { t, lang } = useI18n()
  const { pathname } = useLocation()
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
      aria-label={t("nav.menu")}
    >
      {BOTTOM.map((item) => {
        const active = isActive(pathname, item)
        return (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            aria-label={t(item.label)}
            className={cn(
              "flex h-14 flex-col items-center justify-center gap-1 text-[11px]",
              active ? "text-primary" : "text-muted-foreground"
            )}
          >
            <item.icon className="size-5" strokeWidth={1.75} />
            <span className="max-w-full truncate px-1">
              {item.to === "/app/input"
                ? lang === "kk"
                  ? "Деректер"
                  : "Данные"
                : t(item.label)}
            </span>
          </NavLink>
        )
      })}
    </nav>
  )
}

function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [pathname])
  return null
}

export function AppShell() {
  const { auth, signOut } = useSession()
  const { t } = useI18n()
  const wide = typeof window !== "undefined" && window.innerWidth >= 1280
  return (
    <SidebarProvider defaultOpen={wide}>
      <ScrollToTop />
      <CriticalWatcher />
      <Sidebar collapsible="icon">
        <SidebarHeader className="h-14 justify-center border-b px-3">
          <NavLink
            to="/app"
            aria-label="Fibo"
            className="flex items-center gap-2 overflow-hidden"
          >
            <Brand />
          </NavLink>
        </SidebarHeader>
        <SidebarContent className="gap-0">
          <NavGroup title="nav.groupWork" items={MAIN} />
          <NavGroup title="nav.groupMore" items={MORE} />
        </SidebarContent>
        <SidebarFooter className="border-t p-2 group-data-[collapsible=icon]:hidden">
          <div className="flex min-w-0 flex-col px-2 py-1">
            <span className="truncate text-sm font-medium">
              {auth?.user.full_name}
            </span>
            <span className="truncate text-xs text-muted-foreground">
              {auth?.user.email}
            </span>
          </div>
          <Button
            variant="ghost"
            className="justify-start md:hidden"
            onClick={signOut}
          >
            <LogOutIcon data-icon="inline-start" />
            {t("auth.signOut")}
          </Button>
        </SidebarFooter>
        <SidebarRail />
      </Sidebar>
      <SidebarInset className="min-w-0 bg-background">
        <TopBar />
        <main className="mx-auto flex w-full max-w-[1480px] min-w-0 flex-col gap-8 px-4 pt-6 pb-24 sm:px-6 md:pb-10 lg:px-8">
          <Outlet />
        </main>
        <BottomNav />
      </SidebarInset>
    </SidebarProvider>
  )
}
