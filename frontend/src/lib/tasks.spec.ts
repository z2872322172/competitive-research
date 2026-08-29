import { describe, expect, it } from 'vitest'

import {
  buildTaskRecoveryFeedback,
  buildTaskListQuery,
  buildTaskSummaries,
  buildTaskSummary,
  getAvailableTaskActions,
  getRunHistory,
  getTaskStatusMeta,
} from './tasks'
import type { ResearchTaskOut, TaskDetailOut, TaskRunOut } from '@/api/types'

// 测试辅助：补齐必填字段的最小任务对象。
function task(overrides: Partial<ResearchTaskOut> = {}): ResearchTaskOut {
  return {
    id: 1,
    title: 'Cursor pricing research',
    prompt: 'Research Cursor pricing',
    scope: {
      competitors: ['Cursor', 'Trae'],
      dimensions: ['pricing', 'enterprise'],
      report_depth: 'standard',
      time_range: 'last_12_months',
    },
    status: 'failed',
    workspace_id: 'default',
    current_run_id: 2,
    failure_reason: 'source_discovery_missing',
    created_by: 'local-user',
    confirmed_at: '2026-08-15T08:00:00Z',
    queued_at: '2026-08-15T08:00:01Z',
    completed_at: null,
    created_at: '2026-08-15T07:58:00Z',
    updated_at: '2026-08-15T08:03:00Z',
    ...overrides,
  }
}

describe('getTaskStatusMeta', () => {
  it('exposes retryable failed state with reason', () => {
    const meta = getTaskStatusMeta(task(), { id: 2, status: 'failed', error_message: 'fetch timeout' } as TaskRunOut)

    expect(meta.label).toBe('失败')
    expect(meta.tone).toBe('failed')
    expect(meta.reason).toBe('fetch timeout')
    expect(meta.canRetry).toBe(true)
    expect(meta.canCancel).toBe(false)
  })
})

describe('buildTaskListQuery', () => {
  it('trims search and omits all-status filter', () => {
    expect(buildTaskListQuery('  cursor  ', 'all')).toEqual({ limit: 20, q: 'cursor' })
    expect(buildTaskListQuery('', 'running')).toEqual({ limit: 20, status: 'running' })
  })
})

describe('buildTaskSummary', () => {
  it('counts detail artifacts and keeps status reason', () => {
    const summary = buildTaskSummary(task(), {
      task: task(),
      latest_run: { id: 2, status: 'failed', error_message: 'fetch timeout' } as TaskRunOut,
      runs: [],
      sources: [],
      evidence: [{ id: 1 }, { id: 2 }] as TaskDetailOut['evidence'],
      claims: [{ id: 1 }] as TaskDetailOut['claims'],
      reports: [{ citation_coverage: 0.75 }] as TaskDetailOut['reports'],
    })

    expect(summary.evidenceCount).toBe(2)
    expect(summary.claimCount).toBe(1)
    expect(summary.coverage).toBe(75)
    expect(summary.statusReason).toBe('fetch timeout')
  })

  it('includes the research mode in the scope preview', () => {
    const summary = buildTaskSummary(
      task({ scope: { ...task().scope, research_type: 'deep_research' } }),
      {
        task: task(),
        latest_run: { id: 2, status: 'failed', error_message: 'fetch timeout' } as TaskRunOut,
        runs: [],
        sources: [],
        evidence: [],
        claims: [],
        reports: [],
      },
    )

    expect(summary.scope).toMatch(/深度研究/)
  })
})

describe('buildTaskSummaries', () => {
  it('uses the matching cached detail for every task row', () => {
    const rows = buildTaskSummaries(
      [
        task({ id: 1, title: 'First task', updated_at: '2026-08-15T08:03:00Z' }),
        task({ id: 2, title: 'Second task', status: 'completed', updated_at: '2026-08-15T08:04:00Z' }),
      ],
      {
        1: {
          latest_run: { id: 1, status: 'failed', error_message: 'fetch timeout' } as TaskRunOut,
          evidence: [{ id: 1, source_id: 1, quote: 'test', locator: {}, extraction_method: 'test', language: 'en', quality_score: 0.9, source: null }] as any,
          claims: [{ id: 1 }] as any,
          reports: [{ citation_coverage: 0.5 }] as any,
        },
        2: {
          latest_run: { id: 2, status: 'completed', error_message: null } as TaskRunOut,
          evidence: [{ id: 2, source_id: 1, quote: 'test', locator: {}, extraction_method: 'test', language: 'en', quality_score: 0.9, source: null }, { id: 3, source_id: 1, quote: 'test', locator: {}, extraction_method: 'test', language: 'en', quality_score: 0.9, source: null }] as any,
          claims: [{ id: 2 }, { id: 3 }] as any,
          reports: [{ citation_coverage: 0.9 }] as any,
        },
      },
    )

    expect(rows[0].evidenceCount).toBe(1)
    expect(rows[0].statusReason).toBe('fetch timeout')
    expect(rows[1].evidenceCount).toBe(2)
    expect(rows[1].claimCount).toBe(2)
    expect(rows[1].coverage).toBe(90)
  })
})

describe('getRunHistory', () => {
  it('sorts newest first and marks current run separately', () => {
    const runs = getRunHistory(
      [
        { id: 1, status: 'completed', current_stage: 'review_gate', queued_at: '2026-08-15T07:00:00Z', started_at: '2026-08-15T07:01:00Z', finished_at: '2026-08-15T07:03:00Z' },
        { id: 2, status: 'running', current_stage: 'fetch_sources', queued_at: '2026-08-15T08:00:00Z', started_at: '2026-08-15T08:01:00Z', finished_at: null },
      ] as TaskRunOut[],
      2,
    )

    expect(runs[0].id).toBe(2)
    expect(runs[0].isCurrent).toBe(true)
    expect(runs[0].label).toBe('当前 run')
    expect(runs[1].label).toBe('历史 run')
  })
})

describe('getAvailableTaskActions', () => {
  it('enables cancel for active runs and retry for failed tasks', () => {
    expect(getAvailableTaskActions({ status: 'running' }, { status: 'running' })).toEqual({ canOpen: true, canRetry: false, canCancel: true, canResume: false })
    expect(getAvailableTaskActions({ status: 'failed' }, { status: 'failed' })).toEqual({ canOpen: true, canRetry: true, canCancel: false, canResume: true })
    expect(getAvailableTaskActions({ status: 'canceled' }, { status: 'canceled' })).toEqual({ canOpen: true, canRetry: true, canCancel: false, canResume: false })
  })
})

describe('buildTaskRecoveryFeedback', () => {
  it('prefers resume for failed tasks with failed runs', () => {
    const feedback = buildTaskRecoveryFeedback(
      { status: 'failed', failure_reason: 'claim extraction failed' },
      { status: 'failed', error_message: 'schema validation failed' },
    )!

    expect(feedback.tone).toBe('failed')
    expect(feedback.primaryAction).toBe('resume')
    expect(feedback.title).toMatch(/继续执行/)
    expect(feedback.description).toMatch(/schema validation failed/)
  })

  it('explains canceled and active task actions', () => {
    const canceled = buildTaskRecoveryFeedback({ status: 'canceled', failure_reason: 'user changed scope' }, { status: 'canceled' })!
    const active = buildTaskRecoveryFeedback({ status: 'running' }, { status: 'running' })!
    const completed = buildTaskRecoveryFeedback({ status: 'completed' }, { status: 'completed' })

    expect(canceled.primaryAction).toBe('retry')
    expect(active.primaryAction).toBe('cancel')
    expect(completed).toBe(null)
  })
})
