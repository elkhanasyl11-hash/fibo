import { CheckIcon, CopyIcon, MicIcon, CameraIcon, AudioLinesIcon, SendIcon } from "lucide-react"
import QRCode from "qrcode"
import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { useI18n } from "@/i18n"
import { cn } from "@/lib/utils"

// The hand-off to the Telegram bot: deep link that carries the invite code, a QR code for the
// phone in the mechanic's pocket, and the code itself for typing.
export function TelegramConnect({
  link,
  inviteCode,
  className,
  compact = false,
}: {
  link: string | null
  inviteCode: string
  className?: string
  compact?: boolean
}) {
  const { t } = useI18n()
  const [qr, setQr] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!link) return
    let alive = true
    QRCode.toDataURL(link, { margin: 1, width: 320, color: { dark: "#0d253d", light: "#ffffff" } })
      .then((url) => alive && setQr(url))
      .catch(() => alive && setQr(null))
    return () => {
      alive = false
    }
  }, [link])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(inviteCode)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className={cn("grid gap-6 rounded-lg border bg-card p-6 shadow-card md:grid-cols-[1fr_auto]", className)}>
      <div className="flex min-w-0 flex-col gap-5">
        <div className="flex flex-col gap-1.5">
          <h3 className="text-lg font-medium">{t("tg.title")}</h3>
          <p className="text-sm text-muted-foreground text-pretty">{t("tg.body")}</p>
        </div>
        {!compact && (
          <ul className="flex flex-col gap-3 text-sm">
            {[
              { icon: MicIcon, text: t("tg.voice") },
              { icon: AudioLinesIcon, text: t("tg.sound") },
              { icon: CameraIcon, text: t("tg.photo") },
            ].map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-start gap-3">
                <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-md bg-surface text-muted-foreground">
                  <Icon className="size-4" strokeWidth={1.75} />
                </span>
                <span className="text-pretty">{text}</span>
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap items-center gap-3">
          {link ? (
            <Button asChild size="lg">
              <a href={link} target="_blank" rel="noreferrer">
                <SendIcon data-icon="inline-start" />
                {t("tg.open")}
              </a>
            </Button>
          ) : (
            <p className="text-sm text-muted-foreground">{t("tg.noBot")}</p>
          )}
          <button
            type="button"
            onClick={copy}
            className="inline-flex h-11 items-center gap-2 rounded-full border px-4 text-sm transition-colors hover:bg-muted"
          >
            <span className="text-muted-foreground">{t("tg.code")}</span>
            <span className="num font-medium tracking-[0.12em]">{inviteCode}</span>
            {copied ? <CheckIcon className="size-4 text-ok" /> : <CopyIcon className="size-4 text-muted-foreground" />}
          </button>
        </div>
      </div>
      {link && (
        <div className="flex flex-col items-center gap-2 justify-self-center">
          <div className="rounded-lg border bg-white p-3">
            {qr ? (
              <img src={qr} alt={t("tg.qrAlt")} className="size-40" />
            ) : (
              <div className="size-40" />
            )}
          </div>
          <span className="text-xs text-muted-foreground">{t("tg.scan")}</span>
        </div>
      )}
    </div>
  )
}
