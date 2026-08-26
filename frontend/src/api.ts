import { buildScopedRequestHeaders, resolveWorkspaceId } from './researchCompetitors.js'

type RuntimeProcess = { env?: Record<string, string | undefined> }

const viteEnv = import.meta.env ?? {}
const runtimeEnv = (globalThis as typeof globalThis & { process?: RuntimeProcess }).process?.env ?? {}

export const API_BASE_URL = viteEnv.VITE_API_BASE_URL ?? runtimeEnv.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/v1'
const DEFAULT_WORKSPACE_ID = viteEnv.VITE_WORKSPACE_ID ?? runtimeEnv.VITE_WORKSPACE_ID
const DEFAULT_USER_ID = viteEnv.VITE_USER_ID ?? runtimeEnv.VITE_USER_ID

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
}

export type ResearchTaskOut = {
  id: string
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
  current_run_id: string | null
  failure_reason: string | null
  created_by: string
  confirmed_at: string | null
  queued_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

export type TaskRunOut = {
  id: string
  task_id: string
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
  id: string
  task_id: string
  url: string
  canonical_url: string
  source_type: string
  title: string
  publisher: string
  published_at: string | null
  retrieved_at: string
  content_hash: string
  index_status: string
}

export type SourceSnapshotOut = {
  source_id: string
  artifact_type: string
  available: boolean
  content_hash: string | null
  object_key: string | null
  summary: string
  char_count: number
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
  id: string
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
  id: string
  source_id: string
  quote: string
  locator: Record<string, unknown>
  extraction_method: string
  language: string
  quality_score: number
  source: SourceOut | null
}

export type ClaimOut = {
  id: string
  task_id: string
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
  evidence_ids: string[]
  review_decision: string | null
  review_reason: string | null
  reviewed_at: string | null
}

type ApiErrorBody = {
  error?: {
    code?: string
    message?: string
    details?: unknown
  }
}

export type ResearchEventOut = {
  id: string
  run_id: string
  sequence_no: number
  type: string
  stage: string
  message: string
  payload: Record<string, unknown>
  created_at: string
}

export type ReportSectionEvidenceOut = {
  id: string
  source_id: string
  quote: string
  source_title: string | null
  source_url: string | null
  publisher: string | null
  quality_score: number
  relation: string | null
  claim_ids: string[]
}

export type ReportSectionOut = {
  id: string
  section_type: string
  title: string
  content_markdown: string
  order_no: number
  evidence: ReportSectionEvidenceOut[]
}

export type ReportOut = {
  id: string
  task_id: string
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

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...buildScopedRequestHeaders(options.headers, {
        workspaceId: DEFAULT_WORKSPACE_ID,
        userId: DEFAULT_USER_ID,
      }),
    },
  })

  if (!response.ok) {
    const text = await response.text()
    try {
      const body = JSON.parse(text) as ApiErrorBody
      throw new Error(body.error?.message || body.error?.code || `API request failed: ${response.status}`)
    } catch (error) {
      if (error instanceof SyntaxError) throw new Error(text || `API request failed: ${response.status}`)
      throw error
    }
  }

  return response.json() as Promise<T>
}

async function requestBlob(path: string, options: RequestInit = {}): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: buildScopedRequestHeaders(options.headers, {
      workspaceId: DEFAULT_WORKSPACE_ID,
      userId: DEFAULT_USER_ID,
    }),
  })

  if (!response.ok) {
    const text = await response.text()
    try {
      const body = JSON.parse(text) as ApiErrorBody
      throw new Error(body.error?.message || body.error?.code || `API request failed: ${response.status}`)
    } catch (error) {
      if (error instanceof SyntaxError) throw new Error(text || `API request failed: ${response.status}`)
      throw error
    }
  }

  return response.blob()
}

export function listResearchTasks(params: { status?: string; q?: string; workspace_id?: string; created_by?: string; skip?: number; limit?: number } = {}) {
  const search = new URLSearchParams()
  if (params.status) search.set('status', params.status)
  if (params.q) search.set('q', params.q)
  if (params.workspace_id) search.set('workspace_id', params.workspace_id)
  if (params.created_by) search.set('created_by', params.created_by)
  if (params.skip !== undefined) search.set('skip', String(params.skip))
  if (params.limit !== undefined) search.set('limit', String(params.limit))
  const suffix = search.toString() ? `?${search.toString()}` : ''
  return request<ResearchTaskOut[]>(`/research-tasks${suffix}`)
}

export function createResearchTask(payload: ResearchTaskCreate) {
  return request<ResearchTaskOut>('/research-tasks', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getResearchTask(taskId: string, evidenceQuery = '') {
  const suffix = evidenceQuery ? `?${evidenceQuery}` : ''
  return request<TaskDetailOut>(`/research-tasks/${taskId}${suffix}`)
}

export function getSourceSnapshot(sourceId: string) {
  return request<SourceSnapshotOut>(`/sources/${sourceId}/snapshot`)
}

export function listCompetitors(workspaceId = '') {
  return request<CompetitorProfileOut[]>(`/competitors?workspace_id=${encodeURIComponent(resolveWorkspaceId(workspaceId, DEFAULT_WORKSPACE_ID))}`)
}

export function createCompetitor(payload: CompetitorProfileCreate) {
  const workspace_id = resolveWorkspaceId(payload.workspace_id, DEFAULT_WORKSPACE_ID)
  return request<CompetitorProfileOut>('/competitors', {
    method: 'POST',
    body: JSON.stringify({ ...payload, workspace_id }),
  })
}

export function confirmResearchTask(taskId: string, background = false) {
  const suffix = background ? '?background=true' : ''
  return request<TaskRunOut>(`/research-tasks/${taskId}/confirm${suffix}`, {
    method: 'POST',
  })
}

export function rerunResearchTask(taskId: string, background = false) {
  const suffix = background ? '?background=true' : ''
  return request<TaskRunOut>(`/research-tasks/${taskId}/runs${suffix}`, {
    method: 'POST',
  })
}

export function resumeResearchTask(taskId: string, background = false) {
  const suffix = background ? '?background=true' : ''
  return request<TaskRunOut>(`/research-tasks/${taskId}/resume${suffix}`, {
    method: 'POST',
  })
}

export function cancelResearchTask(taskId: string, reason = 'canceled by user') {
  return request<TaskRunOut>(`/research-tasks/${taskId}/cancel`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  })
}

export function listResearchEvents(taskId: string, after = 0) {
  return request<ResearchEventOut[]>(`/research-tasks/${taskId}/events?after=${after}`)
}

export function reviewClaim(claimId: string, decision: 'accept' | 'mark_uncertain' | 'exclude' | 'continue_research', reason = '') {
  return request(`/claims/${claimId}/review`, {
    method: 'POST',
    body: JSON.stringify({ decision, reason }),
  })
}

export function regenerateReport(taskId: string) {
  return request<ReportOut>(`/research-tasks/${taskId}/reports/regenerate`, {
    method: 'POST',
  })
}

export function exportReport(reportId: string, format = 'markdown') {
  return request<{ format: string; content: string }>(`/reports/${reportId}/export?format=${format}`, {
    method: 'POST',
  })
}

export function exportReportArtifact(reportId: string, format: 'pdf' | 'docx') {
  return requestBlob(`/reports/${reportId}/export?format=${format}`, {
    method: 'POST',
  })
}

export function resetDemoData() {
  return request<{ status: string; deleted_tasks: number }>('/dev/demo-data', {
    method: 'DELETE',
  })
}
