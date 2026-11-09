import { useCallback, useEffect, useState } from "react"

import type { Profile, Question, Survey } from "@/lib/types"

const KEY = "fibo.onboarding"

export interface Draft {
  step: number
  profile: Profile | null
  survey: Survey
  questions: Question[]
  questionsKey: string
  questionsSource: "ai" | "builtin" | null
  questionsDegraded: string[]
  answers: Record<string, string | string[]>
}

export const emptyDraft: Draft = {
  step: 0,
  profile: null,
  survey: {
    activity: "",
    team_size: null,
    shifts: null,
    machine_count: null,
    goals: [],
    answers: [],
    questions_source: null,
  },
  questions: [],
  questionsKey: "",
  questionsSource: null,
  questionsDegraded: [],
  answers: {},
}

function load(): Draft {
  try {
    const raw = sessionStorage.getItem(KEY)
    if (!raw) return emptyDraft
    const saved = JSON.parse(raw)
    const profile = [
      "metalworking",
      "bakery",
      "confectionery",
      "sewing",
      "dairy",
    ].includes(saved.profile)
      ? saved.profile
      : null
    return {
      ...emptyDraft,
      ...saved,
      profile,
      step: profile ? Math.max(0, Math.min(3, Number(saved.step) || 0)) : 0,
      survey: { ...emptyDraft.survey, ...saved.survey },
      questions: Array.isArray(saved.questions) ? saved.questions : [],
      answers: saved.answers ?? {},
    }
  } catch {
    return emptyDraft
  }
}

// Survey answers live in the tab until the account is created (sessionStorage, not the server).
export function useDraft() {
  const [draft, setDraft] = useState<Draft>(load)
  useEffect(() => {
    try {
      sessionStorage.setItem(KEY, JSON.stringify(draft))
    } catch {
      // storage blocked: the draft lives in memory only
    }
  }, [draft])
  const update = useCallback(
    (patch: Partial<Draft> | ((current: Draft) => Partial<Draft>)) =>
      setDraft((current) => ({
        ...current,
        ...(typeof patch === "function" ? patch(current) : patch),
      })),
    []
  )
  const updateSurvey = useCallback(
    (patch: Partial<Survey>) =>
      setDraft((current) => ({
        ...current,
        survey: { ...current.survey, ...patch },
      })),
    []
  )
  const reset = useCallback(() => setDraft(emptyDraft), [])
  const clear = () => {
    try {
      sessionStorage.removeItem(KEY)
    } catch {
      // ignore
    }
  }
  return { draft, update, updateSurvey, clear, reset }
}

export function surveyWithAnswers(draft: Draft): Survey {
  const answers = draft.questions
    .filter((q) => {
      const a = draft.answers[q.id]
      return (
        a !== undefined && a !== "" && !(Array.isArray(a) && a.length === 0)
      )
    })
    .map((q) => {
      const raw = draft.answers[q.id]
      const answer = q.kind === "number" ? Number(raw) : raw
      return { question_id: q.id, question: q.label, answer }
    })
  return { ...draft.survey, answers, questions_source: draft.questionsSource }
}
