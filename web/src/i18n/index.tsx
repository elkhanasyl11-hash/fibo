import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react"

import type { Lang } from "@/lib/types"
import { kk } from "./kk"
import { ru, type Key } from "./ru"

const LANG_KEY = "fibo.lang"
const dictionaries: Record<Lang, Record<Key, string>> = { ru, kk }

type Vars = Record<string, string | number>
interface I18n {
  lang: Lang
  setLang: (lang: Lang) => void
  t: (key: Key, vars?: Vars) => string
}

const I18nContext = createContext<I18n | null>(null)

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(LANG_KEY)
    if (saved === "ru" || saved === "kk") return saved
  } catch {
    // storage blocked
  }
  return "ru"
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang)
  const setLang = useCallback((next: Lang) => {
    setLangState(next)
    document.documentElement.lang = next
    try {
      localStorage.setItem(LANG_KEY, next)
    } catch {
      // storage blocked
    }
  }, [])
  const t = useCallback(
    (key: Key, vars?: Vars) => {
      const text = dictionaries[lang][key] ?? ru[key] ?? key
      return vars ? text.replace(/\{(\w+)\}/g, (_, name) => String(vars[name] ?? "")) : text
    },
    [lang]
  )
  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useI18n(): I18n {
  const context = useContext(I18nContext)
  if (!context) throw new Error("useI18n outside I18nProvider")
  return context
}

export type { Key }
