import type { AuthUser } from '@/lib/authSession'

// 后端主键为自增整型，所有 ID 字段均为 number。

export type { AuthUser }

export type AuthTokenResponse = {
  token: string
  token_type: string
  expires_in: number
  user: AuthUser
}

export type ResearchTaskCreate = {
  prompt: string
  title?: string
  research_type?: 'competitive_research' | 'deep_research'
  template?: string
  research_question?: string
  research_aspects?: string[]
  competitors: string[]
  dimensions: string[]
  source_preferences: string[]
  workspace_id?: string
  created_by?: string
  report_depth: string
  time_range: string
  output_format: string
  clarification_answers?: Array<Record<string, unknown>>
  research_weights?: Array<Record<string, unknown>>
  assumptions?: string[]
}

export type ClarificationQuestionOut = {
  key: string
  label: string
  question: string
  reason: string
  answer_type: 'free_text' | 'single_choice' | 'multi_choice'
  options: string[]
  required: boolean
}

export type ResearchPlanSuggestionOut = {
  research_question: string
  detected_domain: string
  detected_intent: string
  research_type: 'competitive_research' | 'deep_research'
  competitors: string[]
  dimensions: string[]
  source_preferences: string[]
  time_range: string
  report_depth: string
  output_format: string
  questions: ClarificationQuestionOut[]
  assumptions: string[]
  warnings: string[]
}

export type ResearchTaskOut = {
  id: number
  title: string
  prompt: string
  scope: {
    competitors?: string[]
    dimensions?: string[]
    research_type?: 'competitive_research' | 'deep_research'
    template?: string
    research_question?: string
    research_aspects?: string[]
    source_preferences?: string[]
    competitor_profile_reuse?: unknown[]
    report_depth?: string
    time_range?: string
    output_format?: string
  }
  status: string
  workspace_id: string
  current_run_id: number | null
  failure_reason: string | null
  created_by: string
  confirmed_at: string | null
  queued_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export type TaskRunOut = {
  id: number
  task_id: number
  status: string
  current_stage: string
  iteration_count: number
  priority: number
  input_snapshot: Record<string, unknown>
  error_message: string | null
  queued_at: string
  started_at: string | null
  finished_at: string | null
}

export type SourceOut = {
  id: number
  task_id: number
  url: string
  canonical_url: string
  source_type: string
  title: string
  publisher: string
  published_at: string | null
  social_platform?: string | null
  sentiment?: string | null
  heat_score?: number | null
  interaction_metrics?: Record<string, unknown>
  retrieved_at: string
  content_hash: string
  index_status: string
  is_primary?: boolean
  reliability?: SourceReliabilityOut | null
}

export type SourceSnapshotOut = {
  source_id: number
  artifact_type: string
  available: boolean
  content_hash: string | null
  object_key: string | null
  summary: string
  char_count: number
}

export type SourceReliabilityOut = {
  score: number
  label: 'high' | 'medium' | 'low'
  reasons: string[]
  warnings: string[]
}

export type CompetitorSourceUrl = {
  label: string
  url: string
  source_type: string
}

export type CompetitorProfileCreate = {
  name: string
  category?: string
  description?: string
  homepage_url?: string
  source_urls?: CompetitorSourceUrl[]
  workspace_id?: string
}

export type CompetitorProfileOut = {
  id: number
  workspace_id: string
  name: string
  category: string
  description: string
  homepage_url: string
  source_urls: CompetitorSourceUrl[]
  source_count: number
  task_count: number
  verified_claim_count: number
  risky_claim_count: number
  report_count: number
  created_at: string
  updated_at: string
}

export type EvidenceOut = {
  id: number
  source_id: number
  quote: string
  locator: Record<string, unknown>
  social_metadata?: Record<string, unknown>
  evidence_hash?: string
  extraction_method: string
  source_version?: number
  language: string
  quality_score: number
  source: SourceOut | null
}

export type ClaimOut = {
  id: number
  task_id: number
  subject: string
  predicate: string
  value: Record<string, unknown>
  claim_type: string
  dimension: string
  status: string
  confidence: string
  confidence_score: number
  display_text: string
  include_in_report: boolean
  evidence_coverage?: number
  evidence_ids: number[]
  evidence_links?: Array<{
    evidence_id: number
    relation: string
    weight: number
  }>
  conflict_analysis?: {
    support_count: number
    conflict_count: number
    context_count: number
    support_score: number
    conflict_score: number
    preferred_relation: string
    needs_more_research: boolean
    recommendation: string
    rationale: string[]
    distinct_source_count?: number
    source_diversity_score?: number
    max_supporting_source_reliability?: number
    confidence_breakdown?: Record<string, number>
  } | null
  review_decision: string | null
  review_reason: string | null
  reviewed_at: string | null
}

export type ResearchEventOut = {
  id: number
  run_id: number
  sequence_no: number
  type: string
  stage: string
  message: string
  payload: Record<string, unknown>
  severity?: string
  actor?: string
  created_at: string
}

export type ReportSectionEvidenceOut = {
  id: number
  source_id: number
  quote: string
  source_title: string | null
  source_url: string | null
  publisher: string | null
  source_type?: string | null
  quality_score: number
  reliability_score?: number | null
  reliability_level?: string | null
  reliability_reasons?: string[]
  relation: string | null
  locator?: Record<string, unknown>
  snapshot_available?: boolean
  content_hash?: string | null
  claim_ids: number[]
}

export type ReportSectionOut = {
  id: number
  section_type: string
  title: string
  content_markdown: string
  order_no: number
  evidence: ReportSectionEvidenceOut[]
}

export type ReportOut = {
  id: number
  task_id: number
  version: number
  status: string
  citation_coverage: number
  input_snapshot: Record<string, unknown>
  generated_at: string | null
  created_at: string
  sections: ReportSectionOut[]
}

export type TaskDetailOut = {
  task: ResearchTaskOut
  latest_run: TaskRunOut | null
  runs: TaskRunOut[]
  sources: SourceOut[]
  evidence: EvidenceOut[]
  claims: ClaimOut[]
  reports: ReportOut[]
}
