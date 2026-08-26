import { buildScopedRequestHeaders, resolveWorkspaceId } from './researchCompetitors.js'
import { authHeaders, activeWorkspaceId, type AuthSession, type AuthUser } from './auth.js'

// 携带登录态的错误：status 为 HTTP 状态码，code 为后端 error.code（如 missing_token）。
export class ApiError extends Error {
  status: number
  code: string

  constructor(message: string, status: number, code: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

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

// 后端主键已改为自增整型，所有 ID 字段为 number。
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
  retrieved_at: string
  content_hash: string
  index_status: string
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
  extraction_method: string
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
  evidence_ids: number[]
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
  id: number
  run_id: number
  sequence_no: number
  type: string
  stage: string
  message: string
  payload: Record<string, unknown>
  created_at: string
}

export type ReportSectionEvidenceOut = {
  id: number
  source_id: number
  quote: string
  source_title: string | null
  source_url: string | null
  publisher: string | null
  quality_score: number
  relation: string | null
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

// 鉴权/工作区头合并：登录态优先（Authorization + 激活工作区），未登录退回环境变量默认值。
function mergedHeaders(headers: HeadersInit | undefined): Record<string, string> {
  const sessionWorkspace = activeWorkspaceId()
  return buildScopedRequestHeaders(headers, {
    workspaceId: sessionWorkspace ?? DEFAULT_WORKSPACE_ID,
    userId: DEFAULT_USER_ID,
    ...authHeaders(),
  } as Record<string, string>)
}

function toApiError(response: Response, text: string): ApiError {
  try {
    const body = JSON.parse(text) as ApiErrorBody
    return new ApiError(
      body.error?.message || body.error?.code || `API request failed: ${response.status}`,
      response.status,
      body.error?.code || 'http_error',
    )
  } catch {
    return new ApiError(text || `API request failed: ${response.status}`, response.status, 'http_error')
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...mergedHeaders(options.headers),
    },
  })

  if (!response.ok) throw toApiError(response, await response.text())

  return response.json() as Promise<T>
}

async function requestBlob(path: string, options: RequestInit = {}): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: mergedHeaders(options.headers),
  })

  if (!response.ok) throw toApiError(response, await response.text())

  return response.blob()
}

// ---------------------------------------------------------------------------
// 鉴权接口
// ---------------------------------------------------------------------------

export type AuthTokenResponse = {
  token: string
  token_type: string
  expires_in: number
  user: AuthUser
}

export function apiRegister(username: string, password: string, workspaceId?: string) {
  const body: Record<string, string> = { username, password }
  if (workspaceId) body.workspace_id = workspaceId
  return request<AuthTokenResponse>('/auth/register', { method: 'POST', body: JSON.stringify(body) })
}

export function apiLogin(username: string, password: string) {
  return request<AuthTokenResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
}

export function apiWhoami() {
  return request<AuthUser>('/auth/me')
}

export function buildAuthSession(response: AuthTokenResponse): AuthSession {
  return { token: response.token, user: response.user }
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

export function getResearchTask(taskId: number, evidenceQuery = '') {
  const suffix = evidenceQuery ? `?${evidenceQuery}` : ''
  return request<TaskDetailOut>(`/research-tasks/${taskId}${suffix}`)
}

export function getSourceSnapshot(sourceId: number) {
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

export function confirmResearchTask(taskId: number, background = false) {
  const suffix = background ? '?background=true' : ''
  return request<TaskRunOut>(`/research-tasks/${taskId}/confirm${suffix}`, {
    method: 'POST',
  })
}

export function rerunResearchTask(taskId: number, background = false) {
  const suffix = background ? '?background=true' : ''
  return request<TaskRunOut>(`/research-tasks/${taskId}/runs${suffix}`, {
    method: 'POST',
  })
}

export function resumeResearchTask(taskId: number, background = false) {
  const suffix = background ? '?background=true' : ''
  return request<TaskRunOut>(`/research-tasks/${taskId}/resume${suffix}`, {
    method: 'POST',
  })
}

export function cancelResearchTask(taskId: number, reason = 'canceled by user') {
  return request<TaskRunOut>(`/research-tasks/${taskId}/cancel`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  })
}

export function listResearchEvents(taskId: number, after = 0) {
  return request<ResearchEventOut[]>(`/research-tasks/${taskId}/events?after=${after}`)
}

export function reviewClaim(claimId: number, decision: 'accept' | 'mark_uncertain' | 'exclude' | 'continue_research', reason = '') {
  return request(`/claims/${claimId}/review`, {
    method: 'POST',
    body: JSON.stringify({ decision, reason }),
  })
}

export function regenerateReport(taskId: number) {
  return request<ReportOut>(`/research-tasks/${taskId}/reports/regenerate`, {
    method: 'POST',
  })
}

export function exportReport(reportId: number, format = 'markdown') {
  return request<{ format: string; content: string }>(`/reports/${reportId}/export?format=${format}`, {
    method: 'POST',
  })
}

export function exportReportArtifact(reportId: number, format: 'pdf' | 'docx') {
  return requestBlob(`/reports/${reportId}/export?format=${format}`, {
    method: 'POST',
  })
}

export function resetDemoData() {
  return request<{ status: string; deleted_tasks: number }>('/dev/demo-data', {
    method: 'DELETE',
  })
}
