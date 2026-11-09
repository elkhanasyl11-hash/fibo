import { useQuery } from "@tanstack/react-query"

import { OwnerTelegram } from "@/components/owner-telegram"
import { PageHeader } from "@/components/page-header"
import { TelegramConnect } from "@/components/telegram-connect"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useI18n, type Key } from "@/i18n"
import { api, query } from "@/lib/api"
import { date } from "@/lib/format"
import { useSession } from "@/lib/session"
import type { User } from "@/lib/types"

const ROLE: Record<User["role"], Key> = { operator: "role.operator", master: "role.master", owner: "role.owner" }

export function TelegramPage() {
  const { t, lang } = useI18n()
  const { auth } = useSession()
  const team = useQuery({
    queryKey: ["users", auth?.workshop.id],
    enabled: auth !== null,
    queryFn: () => api<User[]>(`/users${query({ workshop_id: auth?.workshop.id })}`),
  })
  if (!auth) return null
  const steps: Key[] = ["tgp.s1", "tgp.s2", "tgp.s3", "tgp.s4"]
  return (
    <>
      <PageHeader title={t("tgp.title")} description={t("tgp.lead")} />
      {auth.user.role !== "operator" && <OwnerTelegram />}
      <TelegramConnect link={auth.telegram_link} inviteCode={auth.workshop.invite_code} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-medium">{t("tgp.howTitle")}</CardTitle>
            <CardDescription>{t("tgp.howLead")}</CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="flex flex-col gap-4">
              {steps.map((step, i) => (
                <li key={step} className="grid grid-cols-[28px_1fr] gap-3 text-sm">
                  <span className="num flex size-7 items-center justify-center rounded-full bg-surface text-xs">{i + 1}</span>
                  <span className="pt-1 text-pretty">{t(step, { code: auth.workshop.invite_code })}</span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-medium">{t("tgp.teamTitle")}</CardTitle>
            <CardDescription>{t("tgp.teamLead")}</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col divide-y">
              {(team.data ?? []).map((user) => (
                <li key={user.id} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                  <div className="flex min-w-0 flex-col">
                    <span className="truncate text-sm font-medium">{user.full_name}</span>
                    <span className="text-xs text-muted-foreground">
                      {t(ROLE[user.role])} · {user.telegram_id ? t("tgp.inBot") : t("tgp.webOnly")}
                    </span>
                  </div>
                  <span className="num text-xs text-muted-foreground">{date(user.created_at, lang)}</span>
                </li>
              ))}
            </ul>
            {team.data?.length === 1 && <p className="mt-4 text-sm text-muted-foreground">{t("tgp.alone")}</p>}
          </CardContent>
        </Card>
      </div>
    </>
  )
}
