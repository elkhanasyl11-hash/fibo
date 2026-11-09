import { Field, FieldDescription, FieldGroup, FieldLabel, FieldSet, FieldLegend } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { useI18n } from "@/i18n"
import type { Survey } from "@/lib/types"
import { Chips } from "./chips"

const TEAM: NonNullable<Survey["team_size"]>[] = ["1-5", "6-20", "21-50", "50+"]

export function StepAbout({ survey, onChange }: { survey: Survey; onChange: (patch: Partial<Survey>) => void }) {
  const { t } = useI18n()
  const goals = [t("goal.downtime"), t("goal.first"), t("goal.defects"), t("goal.maintenance"), t("goal.remote")]
  return (
    <FieldGroup>
      <Field>
        <FieldLabel htmlFor="activity">{t("about.activity")}</FieldLabel>
        <Textarea
          id="activity"
          maxLength={300}
          rows={3}
          value={survey.activity}
          placeholder={t("about.activityPh")}
          onChange={(e) => onChange({ activity: e.target.value })}
        />
        <FieldDescription>{t("about.activityHelp")}</FieldDescription>
      </Field>
      <FieldSet>
        <FieldLegend variant="label">{t("about.team")}</FieldLegend>
        <ToggleGroup
          type="single"
          variant="outline"
          value={survey.team_size ?? ""}
          onValueChange={(v) => onChange({ team_size: (v || null) as Survey["team_size"] })}
          className="w-full"
        >
          {TEAM.map((size) => (
            <ToggleGroupItem key={size} value={size} className="num flex-1">
              {size}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </FieldSet>
      <div className="grid gap-6 sm:grid-cols-2">
        <FieldSet>
          <FieldLegend variant="label">{t("about.shifts")}</FieldLegend>
          <ToggleGroup
            type="single"
            variant="outline"
            value={survey.shifts ? String(survey.shifts) : ""}
            onValueChange={(v) => onChange({ shifts: v ? Number(v) : null })}
            className="w-full"
          >
            {["1", "2", "3"].map((n) => (
              <ToggleGroupItem key={n} value={n} className="num flex-1">
                {n}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </FieldSet>
        <Field>
          <FieldLabel htmlFor="machines">{t("about.machines")}</FieldLabel>
          <Input
            id="machines"
            type="number"
            inputMode="numeric"
            min={0}
            max={500}
            className="num"
            value={survey.machine_count ?? ""}
            onChange={(e) => onChange({ machine_count: e.target.value === "" ? null : Math.max(0, Math.min(500, Number(e.target.value))) })}
          />
        </Field>
      </div>
      <FieldSet>
        <FieldLegend variant="label">{t("about.goals")}</FieldLegend>
        <Chips label={t("about.goals")} options={goals} value={survey.goals} onChange={(next) => onChange({ goals: next.slice(0, 8) })} />
      </FieldSet>
    </FieldGroup>
  )
}
