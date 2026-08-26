import type { ResearchTaskOut, TaskDetailOut, TaskRunOut } from './api'

export type TaskStatusTone = 'draft' | 'active' | 'review' | 'done' | 'failed' | 'canceled'

export type TaskStatusMeta = {
  label: string
  tone: TaskStatusTone
  description: string
  rawStatus: string
  reason: string
  canRetry: boolean
  canResume: boolean
  canCancel: boolean
}

export type TaskSummary = {
  id?: number
  title: string
  scope: string
  status: string
  statusTone: TaskStatusTone
  statusReason: string
  statusDescription: string
  evidenceCount: number
  claimCount: number
  coverage: number
  updatedAt: string
  rawStatus: string
  canRetry: boolean
  canResume: boolean
  canCancel: boolean
}

export type TaskListQuery = {
  limit: number
  q?: string
  status?: string
}

export type TaskActions = {
  canOpen: boolean
  canRetry: boolean
  canResume: boolean
  canCancel: boolean
}

export type TaskRecoveryFeedback = {
  tone: 'failed' | 'canceled' | 'active'
  title: string
  description: string
  primaryAction: 'resume' | 'retry' | 'cancel'
}

export type RunHistoryItem = TaskRunOut & {
  isCurrent: boolean
  label: string
  statusLabel: string
  reason: string
}

export function getTaskStatusMeta(task: Partial<ResearchTaskOut> | null | undefined, latestRun?: Partial<TaskRunOut> | null): TaskStatusMeta
export function buildTaskListQuery(searchText?: string, status?: string): TaskListQuery
export function buildTaskSummary(task: Partial<ResearchTaskOut>, detail?: Partial<TaskDetailOut> | null): TaskSummary
export function buildTaskSummaries(tasks?: Partial<ResearchTaskOut>[], detailsById?: Record<string, Partial<TaskDetailOut>>): TaskSummary[]
export function getAvailableTaskActions(task: Partial<ResearchTaskOut>, latestRun?: Partial<TaskRunOut> | null): TaskActions
export function buildTaskRecoveryFeedback(task: Partial<ResearchTaskOut>, latestRun?: Partial<TaskRunOut> | null): TaskRecoveryFeedback | null
export function getRunHistory(runs?: Partial<TaskRunOut>[], currentRunId?: number): RunHistoryItem[]
