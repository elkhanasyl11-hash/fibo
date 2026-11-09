import { CheckIcon, MonitorIcon, MoonIcon, SunIcon } from "lucide-react"

import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { useI18n } from "@/i18n"
import type { Lang } from "@/lib/types"

export function LangToggle() {
  const { lang, setLang, t } = useI18n()
  return (
    <ToggleGroup
      type="single"
      size="sm"
      variant="outline"
      value={lang}
      onValueChange={(value) => value && setLang(value as Lang)}
      aria-label={t("common.language")}
    >
      <ToggleGroupItem value="ru" className="px-2.5 text-xs">
        RU
      </ToggleGroupItem>
      <ToggleGroupItem value="kk" className="px-2.5 text-xs">
        KZ
      </ToggleGroupItem>
    </ToggleGroup>
  )
}

const MODES = [
  { value: "light", icon: SunIcon, label: "theme.light" },
  { value: "dark", icon: MoonIcon, label: "theme.dark" },
  { value: "system", icon: MonitorIcon, label: "theme.system" },
] as const

// Light / Dark / System, stored in localStorage (theme-provider); index.html applies it before paint.
export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const { t } = useI18n()
  const Current = MODES.find((m) => m.value === theme)?.icon ?? MoonIcon
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t("common.theme")}>
          <Current />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-40">
        <DropdownMenuGroup>
          {MODES.map(({ value, icon: Icon, label }) => (
            <DropdownMenuItem key={value} onSelect={() => setTheme(value)}>
              <Icon />
              {t(label)}
              {theme === value && <CheckIcon className="ml-auto" />}
            </DropdownMenuItem>
          ))}
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
