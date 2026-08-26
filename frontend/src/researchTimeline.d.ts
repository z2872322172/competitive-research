import type { ResearchEventOut, TaskRunOut } from './api'

export type ResearchTimelineStatus = 'started' | 'succeeded' | 'failed' | 'skipped' | 'retrying'

export type ResearchTimelineItem = {
  key: string
  nodeName: string
  label: string
  description?: string
  status: ResearchTimelineStatus
  statusLabel: string
  startedAt: string
  updatedAt: string
  durationMs: number
  summary: string
  error: string
}

export type ResearchAuditEvent = {
  type: string
  rawType: string
  time: string
  text: string
  detail: string
}

export type ResearchWorkbenchSummary = {
  completedNodes: number
  totalNodes: number
  progressPercent: number
  currentStageLabel: string
  evidenceCount: number
  claimCount: number
  statusCounts: {
    started: number
    succeeded: number
    failed: number
    skipped: number
    retrying: number
  }
  failureReason: string
}

export function buildResearchTimeline(events: ResearchEventOut[], latestRun?: TaskRunOut | null): ResearchTimelineItem[]

export function buildAuditEvents(events: ResearchEventOut[]): ResearchAuditEvent[]

export function buildResearchWorkbenchSummary(
  events: ResearchEventOut[],
  counts?: { evidenceCount?: number; claimCount?: number },
  latestRun?: TaskRunOut | null,
): ResearchWorkbenchSummary

export function formatDuration(durationMs: number): string
