import { useMutation } from "@tanstack/react-query"
import { ArrowLeftIcon, ArrowRightIcon } from "lucide-react"
import { useEffect, useState } from "react"
import { Link, useNavigate, useSearchParams } from "react-router"

import { Brand } from "@/components/brand"
import { LangToggle, ThemeToggle } from "@/components/toggles"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Spinner } from "@/components/ui/spinner"
import { useI18n, type Key } from "@/i18n"
import { api, ApiError } from "@/lib/api"
import { useSession } from "@/lib/session"
import type { AuthResponse, Profile } from "@/lib/types"
import { surveyWithAnswers, useDraft } from "./draft"
import { supabase, supabaseAuth, authMessage } from "@/lib/supabase"
import { INDUSTRIES } from "./industries"
import {
  accountErrors,
  emptyAccount,
  StepAccount,
  type AccountValues,
} from "./step-account"
import { StepAbout } from "./step-about"
import { StepIndustry } from "./step-industry"
import { StepQuestions } from "./step-questions"

const STEPS: { title: Key; lead: Key }[] = [
  { title: "onb.industryTitle", lead: "onb.industryLead" },
  { title: "onb.aboutTitle", lead: "onb.aboutLead" },
  { title: "onb.questionsTitle", lead: "onb.questionsLead" },
  { title: "onb.accountTitle", lead: "onb.accountLead" },
]

export function OnboardingPage() {
  const { t, lang } = useI18n()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { auth, loading, signIn } = useSession()
  const { draft, update, updateSurvey, clear, reset } = useDraft()
  const [account, setAccount] = useState<AccountValues>(emptyAccount)
  const [showErrors, setShowErrors] = useState(false)

  useEffect(() => {
    const preset = params.get("profile") as Profile | null
    if (
      preset &&
      INDUSTRIES.some((i) => i.id === preset) &&
      draft.step === 0 &&
      !draft.profile
    ) {
      update({ profile: preset })
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const register = useMutation({
    mutationFn: async () => {
      if (supabaseAuth) {
        const { data, error } = await supabase.auth.signUp({
          email: account.email.trim(),
          password: account.password,
          options: {
            emailRedirectTo: `${window.location.origin}/account`,
            data: {
              full_name: account.full_name.trim(),
              language: lang,
              workshop: {
                name: account.workshop_name.trim(),
                city: account.city.trim(),
                profile: draft.profile,
              },
              survey: surveyWithAnswers(draft),
            },
          },
        })
        if (error) throw new Error(authMessage(error))
        return { confirmation: !data.session }
      }
      return api<AuthResponse>("/auth/register", {
        method: "POST",
        json: {
          email: account.email.trim(),
          password: account.password,
          full_name: account.full_name.trim(),
          language: lang,
          workshop: {
            name: account.workshop_name.trim(),
            city: account.city.trim(),
            profile: draft.profile,
          },
          survey: surveyWithAnswers(draft),
        },
      })
    },
    onSuccess: (data) => {
      if ("confirmation" in data) {
        clear()
        navigate(data.confirmation ? "/account?confirm=1" : "/account", {
          replace: true,
        })
        return
      }
      signIn(data)
      clear()
      navigate("/app", { replace: true })
    },
  })

  const step = Math.min(draft.step, 3)
  useEffect(() => {
    // already signed in and no sign-up in progress: nothing to fill in here
    if (auth) navigate("/app", { replace: true })
  }, [auth, draft.profile, draft.step, navigate])
  useEffect(() => {
    // a finished sign-up left in this tab (then signed out): start a fresh one instead of an empty page
    if (!auth && !loading && draft.step === 4) reset()
  }, [auth, loading, draft.step, reset])

  function go(next: number) {
    setShowErrors(false)
    update({ step: next })
    window.scrollTo({ top: 0 })
  }

  const canNext = step === 0 ? draft.profile !== null : true // the description and the questions are optional

  const next = () => {
    if (step === 3) {
      setShowErrors(true)
      if (
        !register.isPending &&
        Object.keys(accountErrors(account)).length === 0
      )
        register.mutate()
      return
    }
    go(step + 1)
  }

  const serverError =
    register.error instanceof ApiError
      ? register.error.code === "api_unavailable" ||
        register.error.code === "invalid_response" ||
        register.error.status === 404 ||
        register.error.status === 405
        ? t("auth.apiUnavailable")
        : register.error.status === 409
          ? t("acc.emailTaken")
          : register.error.status === 0 || register.error.status >= 500
            ? t("common.offline")
            : t("common.error")
      : register.error
        ? supabaseAuth && register.error instanceof Error
          ? register.error.message
          : t("common.error")
        : null

  return (
    <div className="flex min-h-svh flex-col bg-background">
      <header className="mx-auto flex h-16 w-full max-w-3xl items-center justify-between px-4 sm:px-8">
        <Link to="/" aria-label="Fibo">
          <Brand />
        </Link>
        <div className="flex items-center gap-2">
          <LangToggle />
          <ThemeToggle />
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 px-4 pt-4 pb-16 sm:px-8">
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between text-sm text-muted-foreground">
            <span className="num">
              {t("onb.step", { n: step + 1, total: STEPS.length })}
            </span>
            {
              <Link
                to={`/login${account.email.trim() ? `?email=${encodeURIComponent(account.email.trim())}` : ""}`}
                className="transition-colors hover:text-foreground"
              >
                {t("onb.haveAccount")}
              </Link>
            }
          </div>
          <Progress value={((step + 1) / STEPS.length) * 100} className="h-1" />
        </div>
        <section key={step} className="flex flex-col gap-8">
          <div className="flex flex-col gap-2">
            <h1 className="display text-[30px] leading-tight text-balance sm:text-[36px]">
              {t(STEPS[step].title)}
            </h1>
            <p className="text-[15px] text-pretty text-muted-foreground">
              {t(STEPS[step].lead)}
            </p>
          </div>
          {step === 0 && (
            <StepIndustry
              value={draft.profile}
              onChange={(profile) => update({ profile })}
            />
          )}
          {step === 1 && (
            <StepAbout survey={draft.survey} onChange={updateSurvey} />
          )}
          {step === 2 && <StepQuestions draft={draft} update={update} />}
          {step === 3 && (
            <form
              id="register-account"
              onSubmit={(event) => {
                event.preventDefault()
                next()
              }}
            >
              <StepAccount
                values={account}
                onChange={(patch) => setAccount((a) => ({ ...a, ...patch }))}
                showErrors={showErrors}
                serverError={serverError}
              />
            </form>
          )}
        </section>
        {step < 4 && (
          <div className="mt-auto flex items-center justify-between gap-3 border-t pt-6">
            <Button
              variant="ghost"
              onClick={() => go(step - 1)}
              disabled={step === 0}
              className={step === 0 ? "invisible" : undefined}
            >
              <ArrowLeftIcon data-icon="inline-start" />
              {t("common.back")}
            </Button>
            <Button
              size="lg"
              type={step === 3 ? "submit" : "button"}
              form={step === 3 ? "register-account" : undefined}
              onClick={
                step === 3
                  ? undefined
                  : (event) => {
                      event.preventDefault()
                      next()
                    }
              }
              disabled={!canNext || register.isPending}
            >
              {register.isPending && <Spinner data-icon="inline-start" />}
              {step === 3
                ? t("onb.create")
                : step === 2
                  ? t("onb.toAccount")
                  : t("common.next")}
              {!register.isPending && <ArrowRightIcon data-icon="inline-end" />}
            </Button>
          </div>
        )}
      </main>
    </div>
  )
}
