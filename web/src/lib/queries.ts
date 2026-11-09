import { useQueries, useQuery } from "@tanstack/react-query"
import { useMemo } from "react"

import { api, query } from "./api"
import type {
  Incident,
  Machine,
  MachineSummary,
  Manual,
  ProfileConfig,
  Ranking,
  ReportSummary,
  RiskScore,
} from "./types"

export const DAY_MS = 86_400_000
// Live data: operators report from Telegram at any time, so lists refresh on their own.
// Paused while the tab is hidden (react-query default) and refreshed again on return.
export const LIVE_MS = 15_000
export const SLOW_MS = 60_000

export function useProfiles() {
  return useQuery({
    queryKey: ["profiles"],
    staleTime: Infinity,
    queryFn: () => api<ProfileConfig[]>("/profiles"),
  })
}

export function useMachines(workshopId: number | undefined) {
  return useQuery({
    queryKey: ["machines", workshopId],
    enabled: workshopId !== undefined,
    refetchInterval: SLOW_MS,
    queryFn: () =>
      api<Machine[]>(
        `/machines${query({ workshop_id: workshopId, limit: 200 })}`
      ),
  })
}

export function useRanking(workshopId: number | undefined) {
  return useQuery({
    queryKey: ["ranking", workshopId],
    enabled: workshopId !== undefined,
    refetchInterval: LIVE_MS,
    queryFn: () =>
      api<Ranking>(`/risk-scores/ranking${query({ workshop_id: workshopId })}`),
  })
}

export function useIncidents(params: {
  workshop_id?: number
  machine_id?: number
  status?: Incident["status"]
  limit?: number
}) {
  return useQuery({
    queryKey: ["incidents", params],
    enabled:
      params.workshop_id !== undefined || params.machine_id !== undefined,
    refetchInterval: LIVE_MS,
    queryFn: () =>
      api<Incident[]>(`/incidents${query({ limit: 100, ...params })}`),
  })
}

export function useReport(workshopId: number | undefined, days = 30) {
  return useQuery({
    queryKey: ["report", workshopId, days],
    enabled: workshopId !== undefined,
    refetchInterval: SLOW_MS,
    queryFn: () => {
      const from = new Date(Date.now() - days * DAY_MS).toISOString()
      return api<ReportSummary>(
        `/reports/summary${query({ workshop_id: workshopId, from })}`
      )
    },
  })
}

/** Report for an explicit period, e.g. the previous 30 days for a comparison. */
export function useReportRange(
  workshopId: number | undefined,
  fromDaysAgo: number,
  toDaysAgo: number
) {
  return useQuery({
    queryKey: ["report-range", workshopId, fromDaysAgo, toDaysAgo],
    enabled: workshopId !== undefined,
    staleTime: 10 * 60_000,
    queryFn: () => {
      const now = Date.now()
      const from = new Date(now - fromDaysAgo * DAY_MS).toISOString()
      const to = new Date(now - toDaysAgo * DAY_MS).toISOString()
      return api<ReportSummary>(
        `/reports/summary${query({ workshop_id: workshopId, from, to })}`
      )
    },
  })
}

/** Risk histories of many machines at once (shared cache with the heat map and charts). */
export function useHistories(machineIds: number[], days = 30) {
  const results = useQueries({
    queries: machineIds.map((id) => riskHistoryQuery(id, days)),
  })
  const pending = results.some((r) => r.isPending)
  const stamp = results.map((r) => r.dataUpdatedAt).join(",")
  const ids = machineIds.join(",")
  // rebuilt only when a history was refetched or the machine list changed (stable identity for charts)
  const map = useMemo(
    () =>
      new Map(
        machineIds.map(
          (id, i) => [id, results[i]?.data ?? []] as [number, RiskScore[]]
        )
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [stamp, ids]
  )
  return { histories: map, pending }
}

export function useMachineSummary(machineId: number | undefined) {
  return useQuery({
    queryKey: ["machine-summary", machineId],
    enabled: machineId !== undefined,
    refetchInterval: LIVE_MS,
    queryFn: () => api<MachineSummary>(`/machines/${machineId}/summary`),
  })
}

export function riskHistoryQuery(machineId: number, days: number) {
  return {
    queryKey: ["risk-history", machineId, days],
    refetchInterval: SLOW_MS,
    queryFn: () => {
      const from = new Date(Date.now() - days * DAY_MS).toISOString()
      // daily=true: the last score of each local day (the scheduler stores one every hour)
      const offset = -new Date().getTimezoneOffset()
      return api<RiskScore[]>(
        `/machines/${machineId}/risk-history${query({ from, daily: "true", utc_offset_minutes: offset })}`
      )
    },
  }
}

export function useManuals(machineId: number | undefined) {
  return useQuery({
    queryKey: ["manuals", machineId],
    enabled: machineId !== undefined,
    queryFn: () => api<Manual[]>(`/machines/${machineId}/manuals`),
    refetchInterval: (q) =>
      q.state.data?.some(
        (m) => m.index_status === "pending" || m.index_status === "indexing"
      )
        ? 3000
        : false,
  })
}

export function machineTitle(
  profiles: ProfileConfig[] | undefined,
  type: string,
  lang: "ru" | "kk"
): string {
  for (const profile of profiles ?? []) {
    const entry = profile.equipment_catalog.find((e) => e.type === type)
    if (entry) return (lang === "kk" && entry.title_kk) || entry.title_ru
  }
  return type
}

export function useActivity(workshopId: number | undefined) {
  return useQuery({
    queryKey: ["activity", workshopId],
    enabled: workshopId !== undefined,
    refetchInterval: SLOW_MS,
    queryFn: () =>
      api<import("./types").ActivityResponse>(
        `/reports/activity${query({ workshop_id: workshopId, days: 365, utc_offset_minutes: -new Date().getTimezoneOffset() })}`
      ),
  })
}
