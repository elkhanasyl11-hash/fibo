import { OctagonXIcon } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"

import { useI18n } from "@/i18n"
import { motionTokens, springs } from "@/lib/motion"

// Shown above everything when an open incident tripped the backend's safety layer.
export function SafetyBanner({ open, detail }: { open: boolean; detail?: string | null }) {
  const { t } = useI18n()
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="safety"
          role="alert"
          className="sticky top-0 z-40 -mx-4 mb-6 flex items-start gap-3 bg-crit px-4 py-4 text-white sm:-mx-8 sm:px-8"
          initial={{ opacity: 0, y: -motionTokens.distance.md }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -motionTokens.distance.md }}
          transition={springs.snappy}
        >
          <OctagonXIcon className="mt-0.5 size-6 shrink-0" strokeWidth={1.75} />
          <div className="flex min-w-0 flex-col gap-1">
            <p className="text-lg font-medium">{t("safety.title")}</p>
            <p className="text-sm text-white/85">{detail || t("safety.body")}</p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
