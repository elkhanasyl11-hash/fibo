import { useQuery } from "@tanstack/react-query"
import { RefreshCwIcon } from "lucide-react"
import { useEffect, useMemo } from "react"

import { Button } from "@/components/ui/button"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupInput,
  InputGroupText,
} from "@/components/ui/input-group"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { useI18n } from "@/i18n"
import { api } from "@/lib/api"
import type { Question, QuestionsResponse } from "@/lib/types"
import { Chips } from "./chips"
import type { Draft } from "./draft"
import { fallbackQuestions } from "./questions-fallback"

function QuestionField({
  q,
  value,
  onChange,
}: {
  q: Question
  value: string | string[] | undefined
  onChange: (v: string | string[]) => void
}) {
  if (q.kind === "multi") {
    return (
      <FieldSet>
        <FieldLegend variant="label">{q.label}</FieldLegend>
        {q.help && <FieldDescription>{q.help}</FieldDescription>}
        <Chips
          label={q.label}
          options={q.options}
          value={Array.isArray(value) ? value : []}
          onChange={onChange}
        />
      </FieldSet>
    )
  }
  if (q.kind === "single") {
    return (
      <FieldSet>
        <FieldLegend variant="label">{q.label}</FieldLegend>
        {q.help && <FieldDescription>{q.help}</FieldDescription>}
        <ToggleGroup
          type="single"
          variant="outline"
          value={typeof value === "string" ? value : ""}
          onValueChange={(v) => onChange(v)}
          className="flex-wrap justify-start"
        >
          {q.options.map((option) => (
            <ToggleGroupItem
              key={option}
              value={option}
              className="h-auto min-h-9 py-1.5 whitespace-normal"
            >
              {option}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </FieldSet>
    )
  }
  return (
    <Field>
      <FieldLabel htmlFor={`q-${q.id}`}>{q.label}</FieldLabel>
      <InputGroup>
        <InputGroupInput
          id={`q-${q.id}`}
          type={q.kind === "number" ? "number" : "text"}
          inputMode={q.kind === "number" ? "decimal" : "text"}
          min={q.kind === "number" ? 0 : undefined}
          maxLength={200}
          className={q.kind === "number" ? "num" : undefined}
          value={typeof value === "string" ? value : ""}
          onChange={(e) => onChange(e.target.value)}
        />
        {q.unit && (
          <InputGroupAddon align="inline-end">
            <InputGroupText>{q.unit}</InputGroupText>
          </InputGroupAddon>
        )}
      </InputGroup>
      {q.help && <FieldDescription>{q.help}</FieldDescription>}
    </Field>
  )
}

export function StepQuestions({
  draft,
  update,
}: {
  draft: Draft
  update: (patch: Partial<Draft> | ((current: Draft) => Partial<Draft>)) => void
}) {
  const { lang } = useI18n()
  const key = `${draft.profile}|${lang}|${draft.survey.activity.trim()}`
  const local = useMemo(
    () => (draft.profile ? fallbackQuestions[draft.profile][lang] : []),
    [draft.profile, lang]
  )
  const fresh = draft.questionsKey === key && draft.questions.length > 0
  const request = useQuery({
    queryKey: ["onboarding-questions", key],
    enabled: draft.profile !== null,
    staleTime: Infinity,
    retry: false,
    queryFn: ({ signal }) =>
      api<QuestionsResponse>("/onboarding/questions", {
        method: "POST",
        signal,
        timeoutMs: 8_000,
        json: {
          profile: draft.profile,
          activity: draft.survey.activity.slice(0, 300),
          language: lang,
        },
      }),
  })

  // Install an immediate local set. A late AI response must never erase answers already typed.
  useEffect(() => {
    if (fresh) return
    update({
      questions: local,
      questionsKey: key,
      questionsSource: "builtin",
      questionsDegraded: [],
      answers: {},
    })
  }, [fresh, key, local, update])

  const fields = fresh ? draft.questions : local
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card px-4 py-3 text-sm">
        <span className="text-muted-foreground">
          {lang === "kk"
            ? "Кез келген сұрақты өткізіп жіберуге болады."
            : "Можно пропустить любой вопрос."}
        </span>
        {request.data?.source === "ai" && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={
              request.isFetching ||
              !request.data ||
              request.data.source !== "ai"
            }
            onClick={() => {
              if (request.data)
                update({
                  questions: request.data.questions,
                  questionsSource: request.data.source,
                  answers: Object.fromEntries(
                    Object.entries(draft.answers).filter(([id]) =>
                      request.data?.questions.some(
                        (question) => question.id === id
                      )
                    )
                  ),
                })
            }}
          >
            <RefreshCwIcon />
            {lang === "kk"
              ? "Сұрақтарды бейімдеу"
              : "Уточнить вопросы под производство"}
          </Button>
        )}
      </div>
      {request.isError && (
        <p role="status" className="text-xs text-muted-foreground">
          {lang === "kk"
            ? "Стандартты сұрақтар қолжетімді. Тіркелуді жалғастыра аласыз."
            : "Доступны стандартные вопросы. Можно продолжить регистрацию."}
        </p>
      )}
      <FieldGroup>
        {fields.map((q) => (
          <QuestionField
            key={q.id}
            q={q}
            value={draft.answers[q.id]}
            onChange={(value) =>
              update((current) => ({
                answers: { ...current.answers, [q.id]: value },
              }))
            }
          />
        ))}
      </FieldGroup>
    </div>
  )
}
