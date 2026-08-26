import type { ResearchEventOut, TaskDetailOut } from './api'

export type ResearchSyncFeedbackTone = 'info' | 'success' | 'warning' | 'error'

export type ResearchSyncFeedback = {
  tone: ResearchSyncFeedbackTone
  title: string
  description: string
  message: string
}

export function shouldPollResearchTask(detail?: TaskDetailOut | null): boolean

export function buildResearchSyncFeedback(options?: {
  detail?: TaskDetailOut | null
  events?: ResearchEventOut[]
  error?: unknown
}): ResearchSyncFeedback | null
