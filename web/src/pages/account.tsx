import { useEffect, useState } from "react"
import type { User } from "@supabase/supabase-js"
import { Link, useNavigate, useSearchParams } from "react-router"
import { Brand } from "@/components/brand"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Spinner } from "@/components/ui/spinner"
import { authMessage, supabase } from "@/lib/supabase"
import { INDUSTRIES } from "@/pages/onboarding/industries"

export function AccountPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const confirmation = params.get("confirm") === "1"

  useEffect(() => {
    let active = true
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      if (active) setUser(session?.user ?? null)
    })
    void supabase.auth
      .getUser()
      .then(({ data, error }) => {
        if (!active) return
        if (data.user) setUser(data.user)
        else if (!confirmation) {
          if (error && error.name !== "AuthSessionMissingError")
            setError(authMessage(error))
          else navigate("/login", { replace: true })
        }
        setLoading(false)
      })
      .catch(() => {
        if (active) {
          setError("Не удалось связаться с сервером. Обновите страницу.")
          setLoading(false)
        }
      })
    return () => {
      active = false
      subscription.unsubscribe()
    }
  }, [confirmation, navigate])

  const metadata = user?.user_metadata ?? {}
  const workshop = metadata.workshop
  return (
    <div className="min-h-svh bg-background">
      <header className="mx-auto flex h-16 max-w-3xl items-center justify-between px-6">
        <Link to="/">
          <Brand />
        </Link>
        {user && (
          <Button
            variant="ghost"
            onClick={async () => {
              const { error } = await supabase.auth.signOut()
              if (error) setError(authMessage(error))
              else navigate("/login", { replace: true })
            }}
          >
            Выйти
          </Button>
        )}
      </header>
      <main className="mx-auto flex max-w-3xl flex-col gap-6 px-6 py-12">
        {loading ? (
          <Spinner />
        ) : user ? (
          <>
            <div>
              <h1 className="display text-3xl">Мой профиль</h1>
              <p className="mt-2 text-muted-foreground">
                Вы вошли в аккаунт Fibo.
              </p>
            </div>
            <Card>
              <CardHeader>
                <CardTitle>{metadata.full_name || "Аккаунт Fibo"}</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="grid gap-5 sm:grid-cols-2">
                  <div>
                    <dt className="text-sm text-muted-foreground">Почта</dt>
                    <dd className="mt-1 break-all">{user.email}</dd>
                  </div>
                  {workshop?.name && (
                    <div>
                      <dt className="text-sm text-muted-foreground">Цех</dt>
                      <dd className="mt-1">{workshop.name}</dd>
                    </div>
                  )}
                  {workshop?.city && (
                    <div>
                      <dt className="text-sm text-muted-foreground">Город</dt>
                      <dd className="mt-1">{workshop.city}</dd>
                    </div>
                  )}
                  {workshop?.profile && (
                    <div>
                      <dt className="text-sm text-muted-foreground">
                        Производство
                      </dt>
                      <dd className="mt-1">
                        {INDUSTRIES.find((i) => i.id === workshop.profile)
                          ?.ru || workshop.profile}
                      </dd>
                    </div>
                  )}
                </dl>
              </CardContent>
            </Card>
            <p
              role="status"
              className="border-t pt-5 text-sm text-muted-foreground"
            >
              Профиль сохранён. Разделы оборудования и аналитики станут доступны
              после подключения сервера Fibo.
            </p>
          </>
        ) : confirmation ? (
          <Card>
            <CardHeader>
              <CardTitle>Подтвердите почту</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <p>
                Откройте письмо от Fibo / Supabase и подтвердите адрес. Затем
                вернитесь на сайт и войдите с указанным паролем.
              </p>
              <Button asChild>
                <Link to="/login">Перейти ко входу</Link>
              </Button>
            </CardContent>
          </Card>
        ) : null}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
      </main>
    </div>
  )
}
