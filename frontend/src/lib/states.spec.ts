import { describe, expect, it } from 'vitest'

import { buildAuditEvents, buildResearchTimeline, buildResearchWorkbenchSummary } from './timeline'
import { buildEvidenceTraceState, buildEvidenceViewModel, buildEvidenceWallItems, filterEvidenceViewModels, snapshotPreviewText } from './evidence'
import { buildClaimQualitySnapshot, buildLowRiskReviewCandidates, buildReviewItems } from './review'
import { getTaskStatusMeta, buildTaskSummary } from './tasks'
import type { EvidenceOut, TaskDetailOut } from '@/api/types'

// ---------- 研究时间线：空事件 ----------

describe('empty timeline states', () => {
  it('buildResearchTimeline returns an empty list when no events exist', () => {
    expect(buildResearchTimeline([])).toEqual([])
  })

  it('buildResearchWorkbenchSummary describes an idle workbench for empty events', () => {
    const summary = buildResearchWorkbenchSummary([], { status: 'queued' } as never, null)

    expect(summary.totalNodes).toBe(0)
    expect(summary.completedNodes).toBe(0)
    expect(summary.progressPercent).toBe(0)
    expect(summary.currentStageLabel).toBe('尚未开始')
    expect(summary.evidenceCount).toBe(0)
    expect(summary.claimCount).toBe(0)
    expect(summary.failureReason).toBe('')
  })

  it('buildAuditEvents returns an empty list without events', () => {
    expect(buildAuditEvents([])).toEqual([])
  })
})

// ---------- 证据墙：空证据 / 无绑定 Claim ----------

describe('empty evidence states', () => {
  it('buildEvidenceWallItems returns empty rows for empty evidence', () => {
    expect(buildEvidenceWallItems([])).toEqual([])
    expect(buildEvidenceWallItems([], [])).toEqual([])
  })

  it('buildEvidenceWallItems keeps evidence rows without bound claims', () => {
    const item = buildEvidenceViewModel(
      {
        id: 1,
        source_id: 1,
        quote: 'Pricing evidence without claims.',
        locator: {},
        extraction_method: 'trafilatura',
        language: 'en',
        quality_score: 0.9,
        source: {
          id: 1,
          url: 'https://example.com/pricing',
          canonical_url: 'https://example.com/pricing',
          source_type: 'official',
          title: 'Pricing',
          publisher: 'Example',
          retrieved_at: '2026-08-14T10:00:00Z',
          content_hash: 'hash',
        },
      } as EvidenceOut,
      0,
    )

    const [row] = buildEvidenceWallItems([item], [])

    expect(row.id).toBe(1)
    expect(row.competitors).toEqual([])
    expect(row.claimTags).toEqual([])
    expect(row.boundClaims).toEqual([])
  })

  it('filterEvidenceViewModels returns empty list for null or empty input', () => {
    expect(filterEvidenceViewModels(null as never)).toEqual([])
    expect(filterEvidenceViewModels([])).toEqual([])
  })

  it('buildEvidenceTraceState keeps a stable idle state for missing evidence', () => {
    const state = buildEvidenceTraceState(null, null, {})

    expect(state.sourceUrl).toBe('')
    expect(state.snapshotStatus).toBe('idle')
  })

  it('snapshotPreviewText keeps unavailable text for a missing snapshot', () => {
    expect(snapshotPreviewText(null, '')).toBe('快照待加载')
  })
})

// ---------- Claim 审核：无 Claim / 无 Evidence ----------

describe('empty review states', () => {
  it('buildReviewItems returns an empty list when there are no claims', () => {
    expect(buildReviewItems([], [])).toEqual([])
  })

  it('buildLowRiskReviewCandidates returns an empty list for empty claims', () => {
    expect(buildLowRiskReviewCandidates([])).toEqual([])
  })

  it('buildClaimQualitySnapshot handles a claim without evidence bindings', () => {
    const snapshot = buildClaimQualitySnapshot({ evidence_ids: [] } as never, [])

    expect(snapshot.evidenceCount).toBe(0)
    expect(snapshot.evidenceSummaries).toEqual([{ id: 0, label: '暂无绑定证据' }])
  })
})

// ---------- 任务列表：缺省状态 / 空详情 ----------

describe('empty task states', () => {
  it('getTaskStatusMeta falls back to the draft state for unknown status', () => {
    const meta = getTaskStatusMeta({ status: 'unknown_status' })
    // 未知状态回落到草稿态文案，但保留原始状态值
    expect(meta.rawStatus).toBe('unknown_status')
    expect(meta.label).toBe('草稿')
    expect(meta.canRetry).toBe(false)
  })

  it('buildTaskSummary handles detail without sources, evidence, claims or reports', () => {
    const summary = buildTaskSummary(
      { id: 1, prompt: 'p', status: 'draft' },
      {
        task: {
          id: 1,
          title: 'test',
          prompt: 'p',
          status: 'draft',
          scope: {},
          workspace_id: 'default',
          current_run_id: null,
          failure_reason: null,
          created_by: 'user',
          confirmed_at: null,
          queued_at: null,
          completed_at: null,
          created_at: '2026-08-15T08:00:00Z',
          updated_at: '2026-08-15T08:00:00Z',
        },
        latest_run: null,
        runs: [],
        sources: [],
        evidence: [],
        claims: [],
        reports: [],
      } as TaskDetailOut,
    )

    expect(summary.evidenceCount).toBe(0)
    expect(summary.claimCount).toBe(0)
    expect(summary.coverage).toBe(0)
    expect(summary.canRetry).toBe(false)
    expect(summary.canResume).toBe(false)
    expect(summary.canCancel).toBe(false)
  })
})
