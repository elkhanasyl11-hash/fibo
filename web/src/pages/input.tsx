import { useSearchParams } from "react-router"

import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Link } from "react-router"
import { PageHeader } from "@/components/page-header"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty"
import { Field, FieldLabel } from "@/components/ui/field"
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useI18n } from "@/i18n"
import { useMachines, useProfiles } from "@/lib/queries"
import { useSession } from "@/lib/session"
import { ReadingsForm } from "./input/readings-form"
import { Simulator } from "./input/simulator"
import { PanelPhotoPage } from "./panel-photo"

export function InputPage() {
  const { t } = useI18n()
  const { auth } = useSession()
  const machines = useMachines(auth?.workshop.id)
  const profiles = useProfiles()
  const profile = profiles.data?.find((p) => p.id === auth?.workshop.profile)
  const [params, setParams] = useSearchParams()
  const rawTab = params.get("tab")
  const tab =
    rawTab && ["simulator", "readings", "photo"].includes(rawTab)
      ? rawTab
      : "readings"
  const machineId = params.get("machine") ?? ""
  const setMachineId = (id: string) =>
    setParams({ tab, machine: id }, { replace: true })
  const machine =
    machines.data?.find((m) => String(m.id) === machineId) ?? machines.data?.[0]

  const picker = (
    <Field className="max-w-xs">
      <FieldLabel htmlFor="input-machine">{t("table.machine")}</FieldLabel>
      <Select
        value={machine ? String(machine.id) : undefined}
        onValueChange={setMachineId}
      >
        <SelectTrigger id="input-machine" className="w-full">
          <SelectValue placeholder={t("panel.pickMachine")} />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            {machines.data?.map((m) => (
              <SelectItem key={m.id} value={String(m.id)}>
                {m.name}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
    </Field>
  )

  return (
    <>
      <PageHeader title={t("input.title")} description={t("input.lead")} />
      {machines.isPending || profiles.isPending ? (
        <Skeleton className="h-80 w-full" />
      ) : machines.isError || profiles.isError ? (
        <div role="alert" className="rounded-lg border p-6">
          <p>{t("common.error")}</p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => {
              machines.refetch()
              profiles.refetch()
            }}
          >
            {t("common.retry")}
          </Button>
        </div>
      ) : machines.data?.length === 0 ? (
        <Empty className="border bg-card shadow-card">
          <EmptyHeader>
            <EmptyTitle>{t("dash.emptyTitle")}</EmptyTitle>
            <EmptyDescription>{t("dash.empty")}</EmptyDescription>
            <Button asChild>
              <Link to="/app/machines/new">{t("machines.addFirst")}</Link>
            </Button>
          </EmptyHeader>
        </Empty>
      ) : (
        <Tabs
          value={tab}
          onValueChange={(v) =>
            setParams(
              { tab: v, ...(machine ? { machine: String(machine.id) } : {}) },
              { replace: true }
            )
          }
        >
          <TabsList>
            <TabsTrigger value="readings" className="h-10 px-4">
              {t("input.readings")}
            </TabsTrigger>
            <TabsTrigger value="photo" className="h-10 px-4">
              {t("input.photo")}
            </TabsTrigger>
            <TabsTrigger value="simulator" className="h-10 px-4">
              {t("input.simulator")}
            </TabsTrigger>
          </TabsList>
          <TabsContent value="simulator" className="mt-6 flex flex-col gap-4">
            {picker}
            {machine && (
              <Simulator key={machine.id} machine={machine} profile={profile} />
            )}
          </TabsContent>
          <TabsContent value="readings" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-base font-medium">
                  {t("input.readingsTitle")}
                </CardTitle>
                <CardDescription>{t("reading.lead")}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-6">
                {picker}
                {machine && profile && (
                  <ReadingsForm
                    key={machine.id}
                    machine={machine}
                    profile={profile}
                  />
                )}
              </CardContent>
            </Card>
          </TabsContent>
          <TabsContent value="photo" className="mt-6 flex flex-col gap-6">
            <PanelPhotoPage embedded />
          </TabsContent>
        </Tabs>
      )}
    </>
  )
}
