// Shapes of the backend API (backend/app/schemas). Money arrives as a decimal string.

export type Profile =
  "metalworking" | "bakery" | "confectionery" | "sewing" | "dairy"
export type Lang = "ru" | "kk"
export type Level = "normal" | "warning" | "critical"
export type Money = string

export interface Workshop {
  id: number
  name: string
  city: string
  profile: Profile
  invite_code: string
  is_demo: boolean
  survey: Survey | null
  created_at: string
}

export interface User {
  id: number
  telegram_id: number | null
  full_name: string
  role: "operator" | "master" | "owner"
  workshop_id: number
  language: Lang
  email: string | null
  created_at: string
}

export interface AuthResponse {
  token: string
  user: User
  workshop: Workshop
  telegram_link: string | null
}

export interface SurveyAnswer {
  question_id: string
  question: string
  answer: string | string[] | number
}

export interface Survey {
  activity: string
  team_size: "1-5" | "6-20" | "21-50" | "50+" | null
  shifts: number | null
  machine_count: number | null
  goals: string[]
  answers: SurveyAnswer[]
  questions_source: "ai" | "builtin" | null
}

export interface Question {
  id: string
  label: string
  help: string
  kind: "single" | "multi" | "text" | "number"
  options: string[]
  unit: string
}

export interface QuestionsResponse {
  source: "ai" | "builtin"
  questions: Question[]
  degraded: string[]
}

export interface EquipmentType {
  type: string
  title_ru: string
  title_kk: string | null
  default_criticality: number
}

export interface ExtraField {
  name: string
  title_ru: string
  title_kk: string | null
  unit: string
}

export interface ProfileConfig {
  id: Profile
  title_ru: string
  title_kk: string
  model_applicable: boolean
  reading_ranges: Record<string, [number, number]>
  extra_fields: ExtraField[]
  equipment_catalog: EquipmentType[]
}

export interface Machine {
  id: number
  workshop_id: number
  name: string
  type: string
  model: string | null
  criticality: number
  downtime_cost_per_hour_kzt: Money
  avg_repair_hours: number
  last_maintenance_at: string | null
  maintenance_interval_hours: number | null
  batch_value_kzt: Money | null
  tool_changed_at: string | null
  is_demo: boolean
  created_at: string
}

export interface ShapFactor {
  feature: string
  title_ru: string
  value: number | null
  contribution: number
  source?: string
}

export interface Signal {
  name: string
  title_ru: string
  value: number | null
  weight: number
}

export interface RiskScore {
  id: number | null
  machine_id: number
  computed_at: string
  failure_probability: number | null
  risk_index: number
  priority_kzt: Money
  is_anomaly: boolean
  inputs_used: string[]
  model_version: string
  is_demo: boolean
  shap_top3: ShapFactor[]
  signals: Signal[]
  assumptions: { code?: string; text_ru?: string }[]
  model_not_used_reasons: string[]
  anomaly_reason: string | null
}

export interface RankingItem {
  machine_id: number
  machine_name: string
  machine_type: string
  criticality: number
  is_demo: boolean
  score: RiskScore
}

export interface Ranking {
  workshop_id: number
  items: RankingItem[]
  unscored_machine_ids: number[]
}

export interface Incident {
  id: number
  machine_id: number
  user_id: number | null
  input_type: "voice" | "audio" | "photo" | "text"
  status: "received" | "processing" | "open" | "resolved" | "failed"
  level: Level | null
  confidence: number | null
  transcript: string | null
  verdict: string | null
  causes: unknown[]
  manual_pages: number[]
  card_text: string | null
  safety_triggered: boolean
  audio_zscore: number | null
  error_message: string | null
  downtime_hours: number | null
  loss_kzt: Money | null
  created_at: string
  resolved_at: string | null
  is_demo: boolean
  ai_source: "ai" | "builtin" | null
  degraded: string[]
}

export interface Attachment {
  id: number
  kind: string
  file_path: string
  created_at: string
  url: string
}

export interface IncidentDetail extends Incident {
  attachments: Attachment[]
}

export interface Reading {
  id: number
  machine_id: number
  recorded_at: string
  source: "panel" | "form" | "bot"
  spindle_rpm: number | null
  load_pct: number | null
  temperature_c: number | null
  operating_hours: number | null
  extra: Record<string, number> | null
  is_demo: boolean
}

export interface MachineSummary {
  machine: Machine
  latest_risk: RiskScore | null
  open_incidents: Incident[]
  recent_readings: Reading[]
}

export interface WhatIfResponse {
  current: RiskScore
  scenario: RiskScore
  saved: boolean
}

export interface AdviceOption {
  id: string
  title: string
  why: string
  category: "maintenance" | "quality" | "process" | "data"
  scenario: "maintenance" | "tool" | "both" | null
  risk_before: number | null
  risk_after: number | null
  saves_kzt: Money | null
}

export interface AdviceResponse {
  machine_id: number
  source: "ai" | "builtin"
  degraded: string[]
  options: AdviceOption[]
}

export interface ReportSummary {
  workshop_id: number
  period_from: string
  period_to: string
  totals: {
    incidents: number
    failures: number
    downtime_hours: number
    loss_kzt: Money
    ongoing_hours: number
    ongoing_loss_kzt: Money
  }
  top_causes: { cause: string; count: number }[]
  machines: {
    machine_id: number
    machine: string
    incidents: number
    failures: number
    downtime_hours: number
    loss_kzt: Money
    ongoing_hours: number
    ongoing_loss_kzt: Money
    operating_hours: number
    mtbf_hours: number | null
  }[]
}

export interface Manual {
  id: number
  machine_id: number
  original_filename: string
  index_status: "pending" | "indexing" | "ready" | "failed"
  page_count: number | null
  error_message: string | null
  created_at: string
  url: string
}

export interface PanelValue {
  field: string
  value: number | null
  confidence: number
  raw_text: string | null
}

export interface PanelResult {
  machine_id: number
  photo_path: string
  sharpness: number
  brightness: number
  values: PanelValue[]
  rejected: (PanelValue & { reason: string })[]
  extra_fields: string[]
  saved: boolean
}

export interface ChatTurn {
  role: "user" | "assistant"
  content: string
}

export interface AssistantResponse {
  source: "ai" | "builtin"
  degraded: string[]
  answer: string
  referenced_machine_ids: number[]
  referenced_incident_ids: number[]
  tools_used: string[]
  is_demo: boolean
}

export interface Health {
  status: string
  ai_mode?: string
  ai_provider?: string
  [key: string]: unknown
}

export interface ActivityResponse {
  workshop_id: number
  from: string
  to: string
  days: {
    date: string
    readings: number
    incidents: number
    resolved: number
  }[]
}
