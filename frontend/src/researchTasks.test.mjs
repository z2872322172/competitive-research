import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  buildTaskRecoveryFeedback,
  buildTaskListQuery,
  buildTaskSummaries,
  buildTaskSummary,
  getAvailableTaskActions,
  getRunHistory,
  getTaskStatusMeta,
} from './researchTasks.js'

const task = {
  id: 'task-1',
  title: 'Cursor pricing research',
  prompt: 'Research Cursor pricing',
  scope: {
    competitors: ['Cursor', 'Trae'],
    dimensions: ['pricing', 'enterprise'],
    report_depth: 'standard',
    time_range: 'last_12_months',
  },
  status: 'failed',
  current_run_id: 'run-2',
  failure_reason: 'source_discovery_missing',
  created_by: 'local-user',
  confirmed_at: '2026-08-15T08:00:00Z',
  queued_at: '2026-08-15T08:00:01Z',
  completed_at: null,
  created_at: '2026-08-15T07:58:00Z',
  updated_at: '2026-08-15T08:03:00Z',
}

test('getTaskStatusMeta exposes retryable failed state with reason', () => {
  const meta = getTaskStatusMeta(task, { id: 'run-2', status: 'failed', error_message: 'fetch timeout' })

  assert.equal(meta.label, '失败')
  assert.equal(meta.tone, 'failed')
  assert.equal(meta.reason, 'fetch timeout')
  assert.equal(meta.canRetry, true)
  assert.equal(meta.canCancel, false)
})

test('buildTaskListQuery trims search and omits all-status filter', () => {
  assert.deepEqual(buildTaskListQuery('  cursor  ', 'all'), { limit: 20, q: 'cursor' })
  assert.deepEqual(buildTaskListQuery('', 'running'), { limit: 20, status: 'running' })
})

test('buildTaskSummary counts detail artifacts and keeps status reason', () => {
  const summary = buildTaskSummary(task, {
    task,
    latest_run: { id: 'run-2', status: 'failed', error_message: 'fetch timeout' },
    runs: [],
    sources: [],
    evidence: [{ id: 'ev-1' }, { id: 'ev-2' }],
    claims: [{ id: 'claim-1' }],
    reports: [{ citation_coverage: 0.75 }],
  })

  assert.equal(summary.evidenceCount, 2)
  assert.equal(summary.claimCount, 1)
  assert.equal(summary.coverage, 75)
  assert.equal(summary.statusReason, 'fetch timeout')
})

test('buildTaskSummary includes the research mode in the scope preview', () => {
  const summary = buildTaskSummary(
    {
      ...task,
      scope: {
        ...task.scope,
        research_type: 'deep_research',
      },
    },
    {
      task,
      latest_run: { id: 'run-2', status: 'failed', error_message: 'fetch timeout' },
      runs: [],
      sources: [],
      evidence: [],
      claims: [],
      reports: [],
    },
  )

  assert.match(summary.scope, /深度研究/)
})

test('buildTaskSummaries uses the matching cached detail for every task row', () => {
  const rows = buildTaskSummaries(
    [
      { ...task, id: 'task-1', title: 'First task', updated_at: '2026-08-15T08:03:00Z' },
      { ...task, id: 'task-2', title: 'Second task', status: 'completed', updated_at: '2026-08-15T08:04:00Z' },
    ],
    {
      'task-1': {
        latest_run: { id: 'run-1', status: 'failed', error_message: 'fetch timeout' },
        evidence: [{ id: 'ev-1' }],
        claims: [{ id: 'claim-1' }],
        reports: [{ citation_coverage: 0.5 }],
      },
      'task-2': {
        latest_run: { id: 'run-2', status: 'completed', error_message: null },
        evidence: [{ id: 'ev-2' }, { id: 'ev-3' }],
        claims: [{ id: 'claim-2' }, { id: 'claim-3' }],
        reports: [{ citation_coverage: 0.9 }],
      },
    },
  )

  assert.equal(rows[0].evidenceCount, 1)
  assert.equal(rows[0].statusReason, 'fetch timeout')
  assert.equal(rows[1].evidenceCount, 2)
  assert.equal(rows[1].claimCount, 2)
  assert.equal(rows[1].coverage, 90)
})

test('getRunHistory sorts newest first and marks current run separately', () => {
  const runs = getRunHistory([
    { id: 'run-1', status: 'completed', current_stage: 'review_gate', queued_at: '2026-08-15T07:00:00Z', started_at: '2026-08-15T07:01:00Z', finished_at: '2026-08-15T07:03:00Z' },
    { id: 'run-2', status: 'running', current_stage: 'fetch_sources', queued_at: '2026-08-15T08:00:00Z', started_at: '2026-08-15T08:01:00Z', finished_at: null },
  ], 'run-2')

  assert.equal(runs[0].id, 'run-2')
  assert.equal(runs[0].isCurrent, true)
  assert.equal(runs[0].label, '当前 run')
  assert.equal(runs[1].label, '历史 run')
})

test('getAvailableTaskActions enables cancel for active runs and retry for failed tasks', () => {
  assert.deepEqual(getAvailableTaskActions({ status: 'running' }, { status: 'running' }), { canOpen: true, canRetry: false, canCancel: true, canResume: false })
  assert.deepEqual(getAvailableTaskActions({ status: 'failed' }, { status: 'failed' }), { canOpen: true, canRetry: true, canCancel: false, canResume: true })
  assert.deepEqual(getAvailableTaskActions({ status: 'canceled' }, { status: 'canceled' }), { canOpen: true, canRetry: true, canCancel: false, canResume: false })
})

test('buildTaskRecoveryFeedback prefers resume for failed tasks with failed runs', () => {
  const feedback = buildTaskRecoveryFeedback(
    { status: 'failed', failure_reason: 'claim extraction failed' },
    { status: 'failed', error_message: 'schema validation failed' },
  )

  assert.equal(feedback.tone, 'failed')
  assert.equal(feedback.primaryAction, 'resume')
  assert.match(feedback.title, /继续执行/)
  assert.match(feedback.description, /schema validation failed/)
})

test('buildTaskRecoveryFeedback explains canceled and active task actions', () => {
  const canceled = buildTaskRecoveryFeedback({ status: 'canceled', failure_reason: 'user changed scope' }, { status: 'canceled' })
  const active = buildTaskRecoveryFeedback({ status: 'running' }, { status: 'running' })
  const completed = buildTaskRecoveryFeedback({ status: 'completed' }, { status: 'completed' })

  assert.equal(canceled.primaryAction, 'retry')
  assert.equal(active.primaryAction, 'cancel')
  assert.equal(completed, null)
})
