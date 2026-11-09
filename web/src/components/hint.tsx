import { InfoIcon } from "lucide-react"

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

// "What is this and where does it come from" next to every figure.
export function Hint({ text }: { text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={text}
          className="inline-flex size-5 items-center justify-center rounded-full text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          <InfoIcon className="size-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-72 text-pretty">{text}</TooltipContent>
    </Tooltip>
  )
}
