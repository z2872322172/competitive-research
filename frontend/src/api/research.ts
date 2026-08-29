import { request, requestBlob, resolveWorkspaceId, DEFAULT_WORKSPACE_ID } from './client'
import type {
  CompetitorProfileOut,
  ReportOut,
  ResearchPlanSuggestionOut,
  ResearchEventOut,
  ResearchTaskCreate,
  ResearchTaskOut,
  SourceSnapshotOut,
  TaskDetailOut,
  TaskRunOut,
} from './types'

export function clarifyResearchPlan(prompt: string) {
  return request<ResearchPlanSuggestionOut>('/research-plans/clarify', {
    method: 'POST',
    body: JSON.stringify({ prompt }),
  })
}

export function listResearchTasks(
  params: { status?: string; q?: string; workspace_id?: string; created_by?: string; skip?: number; limit?: number } = {},
) {
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

export function reviewClaim(
  claimId: number,
  decision: 'accept' | 'mark_uncertain' | 'exclude' | 'continue_research',
  reason = '',
) {
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

