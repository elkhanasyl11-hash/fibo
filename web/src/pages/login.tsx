import { useMutation } from "@tanstack/react-query"
import { useState } from "react"
import { Link, useNavigate } from "react-router"

import { Brand } from "@/components/brand"
import { LangToggle, ThemeToggle } from "@/components/toggles"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { useI18n } from "@/i18n"
import { api, ApiError } from "@/lib/api"
import { useSession } from "@/lib/session"
import type { AuthResponse } from "@/lib/types"

export function LoginPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const { signIn } = useSession()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const login = useMutation({
    mutationFn: () => api<AuthResponse>("/auth/login", { method: "POST", json: { email: email.trim(), password } }),
    onSuccess: (data) => {
      signIn(data)
      navigate("/app", { replace: true })
    },
  })
  const error =
    login.error instanceof ApiError
      ? login.error.status === 401
        ? t("auth.wrongHint")
        : login.error.status === 429
          ? t("auth.throttled")
          : (login.error.status === 0 || login.error.status >= 500)
            ? t("common.offline")
            : t("common.error")
      : null
  return (
    <div className="flex min-h-svh flex-col bg-background">
      <header className="mx-auto flex h-16 w-full max-w-5xl items-center justify-between px-4 sm:px-8">
        <Link to="/" aria-label="Fibo">
          <Brand />
        </Link>
        <div className="flex items-center gap-2">
          <LangToggle />
          <ThemeToggle />
        </div>
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pt-10 pb-16 sm:pt-20">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle className="display text-2xl">{t("auth.signInTitle")}</CardTitle>
            <CardDescription>{t("auth.signInLead")}</CardDescription>
          </CardHeader>
          <CardContent>
            <form
              id="login"
              onSubmit={(e) => {
                e.preventDefault()
                if (!login.isPending) login.mutate()
              }}
            >
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="email">{t("acc.email")}</FieldLabel>
                  <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
                </Field>
                <Field data-invalid={error ? true : undefined}>
                  <FieldLabel htmlFor="password">{t("acc.password")}</FieldLabel>
                  <Input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    aria-invalid={error ? true : undefined}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </Field>
                {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
              </FieldGroup>
            </form>
          </CardContent>
          <CardFooter className="flex-col items-stretch gap-3 border-t-0 bg-transparent">
            <Button type="submit" form="login" size="lg" disabled={login.isPending}>
              {login.isPending && <Spinner data-icon="inline-start" />}
              {t("auth.signIn")}
            </Button>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="h-px flex-1 bg-border" />
              {t("auth.noAccount")}
              <span className="h-px flex-1 bg-border" />
            </div>
            <Button asChild size="lg" variant="outline">
              <Link to="/start">{t("auth.createAccount")}</Link>
            </Button>
          </CardFooter>
        </Card>
      </main>
    </div>
  )
}
