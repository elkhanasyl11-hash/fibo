import { CheckIcon } from "lucide-react"

import { cn } from "@/lib/utils"

// Multi-choice chips (pill toggles). Single choice uses ToggleGroup; these allow several.
export function Chips({
  options,
  value,
  onChange,
  label,
}: {
  options: string[]
  value: string[]
  onChange: (next: string[]) => void
  label: string
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((option) => {
        const on = value.includes(option)
        return (
          <button
            key={option}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((v) => v !== option) : [...value, option])}
            className={cn(
              "inline-flex h-9 items-center gap-1.5 rounded-full border px-3.5 text-sm transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/40",
              on ? "border-primary bg-primary/8 text-foreground" : "bg-card text-muted-foreground hover:text-foreground"
            )}
          >
            {on && <CheckIcon className="size-3.5 text-primary" strokeWidth={2.5} />}
            {option}
          </button>
        )
      })}
    </div>
  )
}
