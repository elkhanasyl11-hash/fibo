import { useMutation, useQueryClient } from "@tanstack/react-query"
import { BellRingIcon, CheckCircle2Icon, SendIcon } from "lucide-react"
import QRCode from "qrcode"
import { useEffect, useState } from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Spinner } from "@/components/ui/spinner"
import { useI18n } from "@/i18n"
import { api } from "@/lib/api"
import { useSession } from "@/lib/session"

interface LinkResponse {
  link: string | null
  expires_at: number
  linked: boolean
}

const WAIT_POLL_MS = 4000

// The owner attaches their own Telegram (one-hour link from the backend) to get alerts about
// critical incidents and "stop the machine" in the bot. While the link is open, the page checks
// every few seconds whether the bot has confirmed it.
export function OwnerTelegram() {
  const { t } = useI18n()
  const { auth } = useSession()
  const client = useQueryClient()
  const [qr, setQr] = useState<string | null>(null)
  const linked = Boolean(auth?.user.telegram_id)
  const issue = useMutation({ mutationFn: () => api<LinkResponse>("/auth/telegram-link", { method: "POST" }) })
  const link = issue.data?.link ?? null

  useEffect(() => {
    if (!link) return
    let alive = true
    QRCode.toDataURL(link, { margin: 1, width: 280, color: { dark: "#0d253d", light: "#ffffff" } })
      .then((url) => alive && setQr(url))
      .catch(() => alive && setQr(null))
    return () => {
      alive = false
    }
  }, [link])

  useEffect(() => {
    if (!link || linked) return
    const id = setInterval(() => client.invalidateQueries({ queryKey: ["me"] }), WAIT_POLL_MS)
    return () => clearInterval(id)
  }, [link, linked, client])

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base font-medium">
          <BellRingIcon className="size-4 text-muted-foreground" strokeWidth={1.75} />
          {t("owner.title")}
        </CardTitle>
        <CardDescription>{t("owner.lead")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {linked ? (
          <p className="flex items-center gap-2 text-sm text-ok">
            <CheckCircle2Icon className="size-4" />
            {t("owner.linked")}
          </p>
        ) : link ? (
          <div className="flex flex-wrap items-center gap-6">
            <div className="flex flex-col gap-3">
              <Button asChild size="lg">
                <a href={link} target="_blank" rel="noreferrer">
                  <SendIcon data-icon="inline-start" />
                  {t("owner.openBot")}
                </a>
              </Button>
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Spinner className="size-3.5" />
                {t("owner.waiting")}
              </p>
            </div>
            {qr && <img src={qr} alt={t("tg.qrAlt")} className="size-36 rounded-md border bg-white p-2" />}
          </div>
        ) : (
          <div className="flex flex-col items-start gap-2">
            <Button onClick={() => issue.mutate()} disabled={issue.isPending}>
              {issue.isPending ? <Spinner data-icon="inline-start" /> : <SendIcon data-icon="inline-start" />}
              {t("owner.connect")}
            </Button>
            {issue.isSuccess && !link && <p className="text-sm text-muted-foreground">{t("tg.noBot")}</p>}
            {issue.isError && <p className="text-sm text-destructive">{t("common.error")}</p>}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
