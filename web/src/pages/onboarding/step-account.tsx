import { EyeIcon, EyeOffIcon } from "lucide-react"
import { useState } from "react"

import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group"
import { useI18n } from "@/i18n"

export interface AccountValues {
  full_name: string
  workshop_name: string
  city: string
  email: string
  password: string
}

export const emptyAccount: AccountValues = { full_name: "", workshop_name: "", city: "Шымкент", email: "", password: "" }
const EMAIL = /^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$/

export function accountErrors(v: AccountValues): Partial<Record<keyof AccountValues, true>> {
  return {
    ...(v.full_name.trim() ? {} : { full_name: true }),
    ...(v.workshop_name.trim() ? {} : { workshop_name: true }),
    ...(v.city.trim() ? {} : { city: true }),
    ...(EMAIL.test(v.email.trim()) ? {} : { email: true }),
    ...(v.password.length >= 8 ? {} : { password: true }),
  }
}

export function StepAccount({
  values,
  onChange,
  showErrors,
  serverError,
}: {
  values: AccountValues
  onChange: (patch: Partial<AccountValues>) => void
  showErrors: boolean
  serverError: string | null
}) {
  const { t } = useI18n()
  const [visible, setVisible] = useState(false)
  const errors = showErrors ? accountErrors(values) : {}
  const text = (id: keyof AccountValues, label: string, props: React.ComponentProps<typeof Input> = {}, error?: string) => (
    <Field data-invalid={errors[id] ? true : undefined}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input id={id} value={values[id]} aria-invalid={errors[id] ? true : undefined} onChange={(e) => onChange({ [id]: e.target.value })} {...props} />
      {errors[id] && error && <FieldError>{error}</FieldError>}
    </Field>
  )
  return (
    <FieldGroup>
      <div className="grid gap-6 sm:grid-cols-2">
        {text("full_name", t("acc.name"), { autoComplete: "name", maxLength: 150 }, t("acc.required"))}
        {text("workshop_name", t("acc.workshop"), { autoComplete: "organization", maxLength: 150, placeholder: t("acc.workshopPh") }, t("acc.required"))}
      </div>
      {text("city", t("acc.city"), { autoComplete: "address-level2", maxLength: 100 }, t("acc.required"))}
      {text("email", t("acc.email"), { type: "email", autoComplete: "email", inputMode: "email", maxLength: 254 }, t("acc.emailError"))}
      <Field data-invalid={errors.password ? true : undefined}>
        <FieldLabel htmlFor="password">{t("acc.password")}</FieldLabel>
        <InputGroup>
          <InputGroupInput
            id="password"
            type={visible ? "text" : "password"}
            autoComplete="new-password"
            maxLength={128}
            aria-invalid={errors.password ? true : undefined}
            value={values.password}
            onChange={(e) => onChange({ password: e.target.value })}
          />
          <InputGroupAddon align="inline-end">
            <InputGroupButton size="icon-xs" aria-label={visible ? t("acc.hide") : t("acc.show")} onClick={() => setVisible((v) => !v)}>
              {visible ? <EyeOffIcon /> : <EyeIcon />}
            </InputGroupButton>
          </InputGroupAddon>
        </InputGroup>
        {errors.password ? <FieldError>{t("acc.passwordError")}</FieldError> : <FieldDescription>{t("acc.passwordHelp")}</FieldDescription>}
      </Field>
      {serverError && <p role="alert" className="text-sm text-destructive">{serverError}</p>}
    </FieldGroup>
  )
}
