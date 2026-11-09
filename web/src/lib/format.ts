import type { Lang } from "./types"

const locale = (lang: Lang) => (lang === "kk" ? "kk-KZ" : "ru-RU")
// Numbers and tenge: Kazakhstan writes "54 000,5" in both languages; browsers without kk number
// data fall back to "54,000.5", so figures always use the ru-RU format.
const numberLocale = (lang: Lang) => (lang === "kk" ? "ru-RU" : "ru-RU")

export function kzt(value: string | number | null | undefined, lang: Lang = "ru"): string {
  if (value === null || value === undefined || value === "") return "—"
  const number = typeof value === "string" ? Number(value) : value
  return `${new Intl.NumberFormat(numberLocale(lang), { maximumFractionDigits: 0 }).format(number)} ₸`
}

export function num(value: number | null | undefined, digits = 0, lang: Lang = "ru"): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—"
  return new Intl.NumberFormat(numberLocale(lang), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)
}

export function pct(value: number | null | undefined, lang: Lang = "ru"): string {
  if (value === null || value === undefined) return "—"
  return `${num(value * 100, value < 0.1 ? 1 : 0, lang)}%`
}

export function date(value: string | null | undefined, lang: Lang = "ru", withTime = false): string {
  if (!value) return "—"
  return new Intl.DateTimeFormat(locale(lang), {
    day: "numeric",
    month: "short",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(new Date(value))
}

export function dayKey(value: string | Date): string {
  const d = typeof value === "string" ? new Date(value) : value
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

export function daysAgo(value: string | null | undefined): number | null {
  if (!value) return null
  return Math.floor((Date.now() - new Date(value).getTime()) / 86_400_000)
}

/** Compact tenge for big figures on charts: 1,2 млн ₸, 340 тыс ₸. */
export function kztShort(value: number, lang: Lang = "ru"): string {
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `${num(value / 1_000_000, 1, lang)} ${lang === "kk" ? "млн" : "млн"} ₸`
  if (abs >= 10_000) return `${num(value / 1000, 0, lang)} ${lang === "kk" ? "мың" : "тыс"} ₸`
  return kzt(value, lang)
}

/** "5 мин назад" style relative time. */
export function ago(value: string | number, lang: Lang = "ru", now = Date.now()): string {
  const minutes = Math.max(0, Math.round((now - new Date(value).getTime()) / 60_000))
  const kk = lang === "kk"
  if (minutes < 1) return kk ? "қазір" : "только что"
  if (minutes < 60) return kk ? `${minutes} мин бұрын` : `${minutes} мин назад`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return kk ? `${hours} сағ бұрын` : `${hours} ч назад`
  const days = Math.round(hours / 24)
  return kk ? `${days} күн бұрын` : `${days} дн назад`
}
