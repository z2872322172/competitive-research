import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'

import { buildAuditEvents, buildResearchTimeline, buildResearchWorkbenchSummary } from './researchTimeline.js'
import { buildEvidenceTraceState, buildEvidenceViewModel, buildEvidenceWallItems, filterEvidenceViewModels, snapshotPreviewText } from './researchEvidence.js'
import { buildClaimQualitySnapshot, buildLowRiskReviewCandidates, buildReviewItems } from './researchReview.js'
import { getTaskStatusMeta, buildTaskSummary } from './researchTasks.js'

// ---------- 研究时间线：空事件 ----------

test('buildResearchTimeline returns an empty list when no events exist', () => {
  assert.deepEqual(buildResearchTimeline([]), [])
  assert.deepEqual(buildResearchTimeline(null), [])
})

test('buildResearchWorkbenchSummary describes an idle workbench for empty events', () => {
  const summary = buildResearchWorkbenchSummary([], { status: 'queued' }, null)

  assert.equal(summary.totalNodes, 0)
  assert.equal(summary.completedNodes, 0)
  assert.equal(summary.progressPercent, 0)
  assert.equal(summary.currentStageLabel, '尚未开始')
  assert.equal(summary.evidenceCount, 0)
  assert.equal(summary.claimCount, 0)
  assert.equal(summary.failureReason, '')
})

test('buildAuditEvents returns an empty list without events', () => {
  assert.deepEqual(buildAuditEvents([]), [])
})

// ---------- 证据墙：空证据 / 无绑定 Claim ----------

test('buildEvidenceWallItems returns empty rows for empty evidence', () => {
  assert.deepEqual(buildEvidenceWallItems([]), [])
  assert.deepEqual(buildEvidenceWallItems([], []), [])
})

test('buildEvidenceWallItems keeps evidence rows without bound claims', () => {
  const item = buildEvidenceViewModel(
    {
      id: 'evidence-1',
      source_id: 'source-1',
      quote: 'Pricing evidence without claims.',
      locator: {},
      extraction_method: 'trafilatura',
      language: 'en',
      quality_score: 0.9,
      source: {
        id: 'source-1',
        url: 'https://example.com/pricing',
        canonical_url: 'https://example.com/pricing',
        source_type: 'official',
        title: 'Pricing',
        publisher: 'Example',
        retrieved_at: '2026-08-14T10:00:00Z',
        content_hash: 'hash',
      },
    },
    0,
  )

  const [row] = buildEvidenceWallItems([item], [])

  assert.equal(row.id, 'evidence-1')
  assert.deepEqual(row.competitors, [])
  assert.deepEqual(row.claimTags, [])
  assert.deepEqual(row.boundClaims, [])
})

test('filterEvidenceViewModels returns empty list for null or empty input', () => {
  assert.deepEqual(filterEvidenceViewModels(null), [])
  assert.deepEqual(filterEvidenceViewModels([]), [])
})

test('buildEvidenceTraceState keeps a stable idle state for missing evidence', () => {
  const state = buildEvidenceTraceState(null, null, {})

  assert.equal(state.sourceUrl, '')
  assert.equal(state.snapshotStatus, 'idle')
})

test('snapshotPreviewText keeps unavailable text for a missing snapshot', () => {
  assert.equal(snapshotPreviewText(null, ''), '快照待加载')
})

// ---------- Claim 审核：无 Claim / 无 Evidence ----------

test('buildReviewItems returns an empty list when there are no claims', () => {
  assert.deepEqual(buildReviewItems([], []), [])
})

test('buildLowRiskReviewCandidates returns an empty list for empty claims', () => {
  assert.deepEqual(buildLowRiskReviewCandidates([]), [])
})

// ---------- 任务列表：缺省状态 / 空详情 ----------

test('getTaskStatusMeta falls back to the draft state for unknown status', () => {
  const meta = getTaskStatusMeta({ status: 'unknown_status' })
  // 未知状态回落到草稿态文案，但保留原始状态值
  assert.equal(meta.rawStatus, 'unknown_status')
  assert.equal(meta.label, '草稿')
  assert.equal(meta.canRetry, false)
})

test('buildTaskSummary handles detail without sources, evidence, claims or reports', () => {
  const summary = buildTaskSummary({
    task: { id: 'task-1', prompt: 'p', status: 'draft' },
    latest_run: null,
    runs: [],
    sources: [],
    evidence: [],
    claims: [],
    reports: [],
  })

  assert.equal(summary.evidenceCount, 0)
  assert.equal(summary.claimCount, 0)
  assert.equal(summary.coverage, 0)
  assert.equal(summary.canRetry, false)
  assert.equal(summary.canResume, false)
  assert.equal(summary.canCancel, false)
})

// ---------- API 失败状态 ----------

const originalFetch = globalThis.fetch

afterEach(() => {
  globalThis.fetch = originalFetch
})

test('request surfaces network failures as errors', async () => {
  globalThis.fetch = async () => {
    throw new TypeError('Failed to fetch')
  }

  const { getResearchTask } = await import('./api.ts')

  await assert.rejects(getResearchTask('task-1'), /Failed to fetch/)
})

test('request falls back to status text when the error body is empty', async () => {
  globalThis.fetch = async () => new Response('', { status: 500 })

  const { listResearchTasks } = await import('./api.ts')

  await assert.rejects(listResearchTasks(), /API request failed: 500/)
})

test('request prefers the api error code when message is missing', async () => {
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ error: { code: 'validation_error' } }), {
      status: 422,
      headers: { 'Content-Type': 'application/json' },
    })

  const { createResearchTask } = await import('./api.ts')

  await assert.rejects(createResearchTask({ prompt: '' }), /validation_error/)
})

test('request surfaces fastapi validation errors without detail message', async () => {
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ detail: 'prompt must not be empty' }), {
      status: 422,
      headers: { 'Content-Type': 'application/json' },
    })

  const { createResearchTask } = await import('./api.ts')

  await assert.rejects(createResearchTask({ prompt: '' }), /API request failed: 422/)
})
