import { CheckIcon } from "lucide-react"

import { useI18n } from "@/i18n"
import type { Profile } from "@/lib/types"
import { cn } from "@/lib/utils"
import { INDUSTRIES } from "./industries"

export function StepIndustry({ value, onChange }: { value: Profile | null; onChange: (p: Profile) => void }) {
  const { lang } = useI18n()
  return (
    <div role="radiogroup" className="grid gap-3 sm:grid-cols-2">
      {INDUSTRIES.map(({ id, icon: Icon, ru, kk }) => {
        const selected = value === id
        return (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(id)}
            className={cn(
              "flex items-center gap-4 rounded-lg border bg-card p-4 text-left shadow-card transition-[border-color,box-shadow] duration-150 outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
              selected ? "border-primary ring-1 ring-primary" : "hover:border-foreground/20"
            )}
          >
            <span className="flex size-10 shrink-0 items-center justify-center rounded-md bg-surface">
              <Icon className="size-5 text-muted-foreground" strokeWidth={1.5} />
            </span>
            <span className="flex-1 text-[15px] font-medium">{lang === "kk" ? kk : ru}</span>
            <span
              className={cn(
                "flex size-5 items-center justify-center rounded-full border transition-colors",
                selected ? "border-primary bg-primary text-primary-foreground" : "border-input"
              )}
            >
              {selected && <CheckIcon className="size-3" strokeWidth={3} />}
            </span>
          </button>
        )
      })}
    </div>
  )
}
