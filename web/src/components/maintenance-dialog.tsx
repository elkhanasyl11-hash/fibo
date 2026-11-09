import { useMutation, useQueryClient } from "@tanstack/react-query"
import { CalendarCheckIcon, WrenchIcon } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { getPlan, savePlan } from "@/api/mocks/maintenance-plan"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { Textarea } from "@/components/ui/textarea"
import { useI18n } from "@/i18n"
import { api } from "@/lib/api"

const today = () => new Date().toISOString().slice(0, 10)

// "Назначить ТО": the plan (date, who, comment) has no backend endpoint yet and is kept in this
// browser (labelled). "ТО выполнено сегодня" is real: last_maintenance_at, then the risk is recomputed.
export function MaintenanceDialog({
  machine,
  open,
  onOpenChange,
}: {
  machine: { id: number; name: string }
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { t } = useI18n()
  const client = useQueryClient()
  const existing = getPlan(machine.id)
  const [date, setDate] = useState(existing?.date ?? today())
  const [assignee, setAssignee] = useState(existing?.assignee ?? "")
  const [comment, setComment] = useState(existing?.comment ?? "")

  const done = useMutation({
    mutationFn: async () => {
      await api(`/machines/${machine.id}`, { method: "PATCH", json: { last_maintenance_at: new Date().toISOString() } })
      await api("/risk-scores/recompute", { method: "POST", json: { machine_id: machine.id } })
    },
    onMutate: () => onOpenChange(false),
    onSuccess: () => {
      client.invalidateQueries()
      toast.success(t("mnt.doneToast", { machine: machine.name }))
    },
    onError: () => toast.error(t("common.error")),
  })

  const plan = () => {
    savePlan({ machineId: machine.id, date, assignee: assignee.trim(), comment: comment.trim(), createdAt: new Date().toISOString() })
    onOpenChange(false)
    client.invalidateQueries({ queryKey: ["maintenance-plan"] })
    toast.success(t("mnt.plannedToast", { machine: machine.name, date }))
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("mnt.title", { machine: machine.name })}</DialogTitle>
          <DialogDescription>{t("mnt.lead")}</DialogDescription>
        </DialogHeader>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="mnt-date">{t("mnt.date")}</FieldLabel>
            <Input id="mnt-date" type="date" className="num" min={today()} value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
          <Field>
            <FieldLabel htmlFor="mnt-who">{t("mnt.assignee")}</FieldLabel>
            <Input id="mnt-who" maxLength={80} value={assignee} onChange={(e) => setAssignee(e.target.value)} />
          </Field>
          <Field>
            <FieldLabel htmlFor="mnt-comment">{t("mnt.comment")}</FieldLabel>
            <Textarea id="mnt-comment" rows={2} maxLength={300} value={comment} onChange={(e) => setComment(e.target.value)} />
            <FieldDescription>{t("mnt.local")}</FieldDescription>
          </Field>
        </FieldGroup>
        <DialogFooter className="gap-2 sm:justify-between">
          <Button variant="outline" onClick={() => done.mutate()} disabled={done.isPending}>
            {done.isPending ? <Spinner data-icon="inline-start" /> : <WrenchIcon data-icon="inline-start" />}
            {t("mnt.doneNow")}
          </Button>
          <Button onClick={plan} disabled={!date}>
            <CalendarCheckIcon data-icon="inline-start" />
            {t("mnt.plan")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
