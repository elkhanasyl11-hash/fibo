import { createClient } from "@supabase/supabase-js"
import config from "../../supabase.config.json"

// The publishable key is public browser configuration, never a service-role key.
export const supabaseAuth =
  import.meta.env.VITE_AUTH_PROVIDER === "supabase" ||
  (import.meta.env.PROD &&
    import.meta.env.MODE !== "test" &&
    !import.meta.env.VITE_API_URL)

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL || config.url,
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || config.publishableKey,
  { auth: { storageKey: "fibo.supabase.auth", detectSessionInUrl: true } }
)

export function authMessage(error: { code?: string; message: string }): string {
  if (error.code === "invalid_credentials") return "Неверная почта или пароль."
  if (error.code === "email_not_confirmed")
    return "Подтвердите почту по ссылке из письма, затем войдите."
  if (error.code === "user_already_exists")
    return "Эта почта уже зарегистрирована. Войдите в аккаунт."
  if (
    error.code === "over_email_send_rate_limit" ||
    error.code === "over_request_rate_limit"
  )
    return "Слишком много попыток. Подождите несколько минут и попробуйте снова."
  return error.message
}
