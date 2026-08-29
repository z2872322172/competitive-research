import { describe, expect, it } from 'vitest'

import {
  buildClaimEvidenceGroups,
  buildClaimQualitySnapshot,
  buildClaimQualityJudgement,
  buildLowRiskReviewCandidates,
  buildReviewItems,
  resolveReviewReason,
  selectReviewItem,
} from './review'
import type { ClaimOut } from '@/api/types'
import type { EvidenceViewModel } from './evidence'

type TestClaim = Partial<ClaimOut> & { evidence_coverage?: number }

// 测试辅助：补齐 ClaimOut 必填字段后构造 Claim。
function claim(overrides: TestClaim): ClaimOut {
  return {
    id: 0,
    task_id: 1,
    subject: '',
    predicate: '',
    value: {},
    claim_type: '',
    dimension: '',
    status: 'verified',
    confidence: 'medium',
    confidence_score: 0,
    display_text: '',
    include_in_report: true,
    evidence_ids: [],
    review_decision: null,
    review_reason: null,
    reviewed_at: null,
    ...overrides,
  } as ClaimOut
}

describe('buildLowRiskReviewCandidates', () => {
  it('returns only safe unreviewed verified claims', () => {
    const candidates = buildLowRiskReviewCandidates([
      claim({ id: 1, status: 'verified', confidence_score: 0.86, evidence_coverage: 0.91, include_in_report: true, evidence_ids: [1], review_decision: null }),
      claim({ id: 2, status: 'verified', confidence_score: 0.8, evidence_coverage: 0.8, include_in_report: true, evidence_ids: [1], review_decision: 'continue_research' }),
      claim({ id: 3, status: 'conflict', confidence_score: 0.95, evidence_coverage: 1, include_in_report: true, evidence_ids: [1], review_decision: null }),
      claim({ id: 4, status: 'verified', confidence_score: 0.95, evidence_coverage: 1, include_in_report: false, evidence_ids: [1], review_decision: null }),
      claim({ id: 5, status: 'verified', confidence_score: 0.95, evidence_coverage: 1, include_in_report: true, evidence_ids: [1], review_decision: 'accept' }),
      claim({ id: 6, status: 'verified', confidence_score: 0.79, evidence_coverage: 1, include_in_report: true, evidence_ids: [1], review_decision: null }),
      claim({ id: 7, status: 'verified', confidence_score: 0.95, evidence_coverage: 1, include_in_report: true, evidence_ids: [], review_decision: null }),
    ])

    expect(candidates.map((item) => item.claimId)).toEqual([1, 2])
    expect(candidates[0].reason).toBe('批量接受：低风险 Claim 已达到置信度和引用覆盖率阈值。')
  })

  it('treats corroborated claims as safe candidates', () => {
    const candidates = buildLowRiskReviewCandidates([
      claim({ id: 11, status: 'corroborated', confidence_score: 0.91, evidence_coverage: 1, include_in_report: true, evidence_ids: [1, 2], review_decision: null }),
      claim({ id: 12, status: 'low_confidence', confidence_score: 0.91, evidence_coverage: 1, include_in_report: true, evidence_ids: [1], review_decision: null }),
    ])

    expect(candidates.map((item) => item.claimId)).toEqual([11])
  })
})

const evidences = [
  {
    id: 1,
    sourceType: 'official',
    type: '官方',
    title: 'Cursor Pricing',
    domain: 'cursor.com/pricing',
    confidence: 86,
    excerpt: 'Business plan includes privacy controls.',
  },
  {
    id: 2,
    sourceType: 'news',
    type: '新闻',
    title: 'Market Update',
    domain: 'news.example',
    confidence: 54,
    excerpt: 'Older market article cites a different price.',
  },
] as unknown as EvidenceViewModel[]

describe('buildReviewItems', () => {
  it('adds quality context and bound evidence summaries', () => {
    const items = buildReviewItems(
      [
        claim({ id: 1, status: 'conflict', confidence_score: 0.62, evidence_coverage: 0.5, display_text: 'Cursor price conflicts across sources.', evidence_ids: [1, 2], review_decision: null }),
        claim({ id: 2, status: 'verified', confidence_score: 0.95, evidence_coverage: 1, display_text: 'Already verified claim.', evidence_ids: [1], review_decision: 'accept' }),
      ],
      evidences,
    )

    expect(items.length).toBe(1)
    expect(items[0].claimId).toBe(1)
    expect(items[0].kind).toBe('冲突')
    expect(items[0].statusLabel).toBe('存在冲突')
    expect(items[0].confidencePercent).toBe(62)
    expect(items[0].coveragePercent).toBe(50)
    expect(items[0].evidenceSummaries.map((item) => item.label)).toEqual([
      '1 · 官方 · 86% · Cursor Pricing',
      '2 · 新闻 · 54% · Market Update',
    ])
  })

  it('keeps continue research claims visible for another decision', () => {
    const items = buildReviewItems(
      [
        claim({ id: 1, status: 'needs_evidence', confidence_score: 0.31, evidence_coverage: 0, display_text: 'Needs more evidence.', evidence_ids: [], review_decision: 'continue_research' }),
      ],
      evidences,
    )

    expect(items.length).toBe(1)
    expect(items[0].claimId).toBe(1)
    expect(items[0].kind).toBe('低置信度')
    expect(items[0].evidenceSummaries[0].label).toBe('暂无绑定证据')
  })

  it('exposes confidence labels for the review panel', () => {
    const items = buildReviewItems(
      [
        claim({ id: 1, status: 'conflict', confidence: 'low', confidence_score: 0.74, evidence_coverage: 0.88, display_text: 'Confidence label should be visible.', evidence_ids: [1], review_decision: null }),
      ],
      evidences,
    )

    expect(items[0].confidenceLabel).toBe('低')
  })

  it('keeps reviewer reasons on visible continue-research claims', () => {
    const items = buildReviewItems(
      [
        claim({
          id: 1,
          status: 'needs_evidence',
          confidence: 'low',
          confidence_score: 0.42,
          evidence_coverage: 0.25,
          display_text: 'Needs more primary evidence.',
          evidence_ids: [],
          review_decision: 'continue_research',
          review_reason: 'Need one official pricing source.',
          reviewed_at: '2026-08-23T10:00:00Z',
        }),
      ],
      evidences,
    )

    expect(items[0].reviewReason).toBe('Need one official pricing source.')
    expect(items[0].reviewedAt).toBe('2026-08-23T10:00:00Z')
  })

  it('prefers backend conflict analysis recommendation when available', () => {
    const items = buildReviewItems(
      [
        claim({
          id: 1,
          status: 'conflict',
          confidence_score: 0.62,
          evidence_coverage: 0.5,
          display_text: 'Conflicting pricing claim.',
          evidence_ids: [1, 2],
          review_decision: null,
          conflict_analysis: {
            support_count: 1,
            conflict_count: 1,
            context_count: 0,
            support_score: 0.88,
            conflict_score: 0.52,
            preferred_relation: 'supports',
            needs_more_research: true,
            recommendation: '支持证据来源质量更高，但需披露冲突来源。',
            rationale: ['支持证据 1 条，平均强度 88%'],
          },
        }),
      ],
      evidences,
    )

    expect(items[0].recommendation).toBe('支持证据来源质量更高，但需披露冲突来源。')
    expect(items[0].conflictAnalysis?.preferred_relation).toBe('supports')
  })
})

describe('buildClaimQualitySnapshot', () => {
  it('exposes confidence, coverage and evidence bindings', () => {
    const snapshot = buildClaimQualitySnapshot(
      claim({ id: 1, status: 'conflict', confidence_score: 0.62, evidence_coverage: 0.5, evidence_ids: [1, 2] }),
      [
        { id: 1, type: '官方', confidence: 86, title: 'Cursor Pricing' },
        { id: 2, type: '新闻', confidence: 54, title: 'Market Update' },
      ] as unknown as EvidenceViewModel[],
    )

    expect(snapshot.confidencePercent).toBe(62)
    expect(snapshot.coveragePercent).toBe(50)
    expect(snapshot.statusLabel).toBe('存在冲突')
    expect(snapshot.evidenceSummaries.map((item) => item.label)).toEqual([
      '1 · 官方 · 86% · Cursor Pricing',
      '2 · 新闻 · 54% · Market Update',
    ])
  })
})

describe('buildClaimEvidenceGroups', () => {
  it('groups claim evidence by support, conflict and context relation', () => {
    const groups = buildClaimEvidenceGroups(
      claim({
        id: 1,
        status: 'conflict',
        evidence_ids: [1, 2],
        evidence_links: [
          { evidence_id: 1, relation: 'supports', weight: 1 },
          { evidence_id: 2, relation: 'conflicts', weight: 0.8 },
          { evidence_id: 3, relation: 'context', weight: 0.5 },
        ],
      }),
      [
        ...evidences,
        {
          id: 3,
          sourceType: 'docs',
          type: '文档',
          title: 'Docs Context',
          domain: 'docs.example',
          confidence: 72,
          excerpt: 'Background docs.',
          reliabilityLabel: 'medium',
          reliabilityScore: 66,
        },
      ] as unknown as EvidenceViewModel[],
    )

    expect(groups.map((group) => [group.relation, group.label, group.items.map((item) => item.id)])).toEqual([
      ['supports', '支持证据', [1]],
      ['conflicts', '冲突证据', [2]],
      ['context', '背景证据', [3]],
    ])
    expect(groups[1].items[0].weight).toBe(0.8)
    expect(groups[2].items[0].reliabilityScore).toBe(66)
  })
})

describe('buildClaimQualityJudgement', () => {
  it('summarizes confidence, coverage, conflict state and evidence bindings', () => {
    const judgement = buildClaimQualityJudgement(
      claim({ id: 1, status: 'conflict', confidence: 'conflict', confidence_score: 0.57, evidence_coverage: 0.5, evidence_ids: [1, 2] }),
      evidences,
    )

    expect(judgement.riskLevel).toBe('high')
    expect(judgement.confidenceText).toBe('57% · 冲突')
    expect(judgement.coverageText).toBe('50%')
    expect(judgement.statusText).toBe('存在冲突')
    expect(judgement.evidenceText).toBe('2 条 Evidence')
    expect(judgement.flags).toEqual(['conflict', 'low_confidence', 'partial_coverage'])
    expect(judgement.flagLabels).toEqual(['存在冲突', '低置信度', '覆盖不足'])
    expect(judgement.evidenceSummaries.map((item) => item.id)).toEqual([1, 2])
  })
})

describe('resolveReviewReason', () => {
  it('prefers typed reviewer reason and falls back to recommendation', () => {
    const item = {
      recommendation: '优先采用官方来源。',
    }

    expect(resolveReviewReason(item, '  官网更可信 ')).toBe('官网更可信')
    expect(resolveReviewReason(item, '   ')).toBe('优先采用官方来源。')
  })
})

describe('selectReviewItem', () => {
  it('returns the requested item or the first visible item', () => {
    const items = [
      { claimId: 1, title: 'First review item' },
      { claimId: 2, title: 'Second review item' },
    ]

    expect(selectReviewItem(items, 2)?.claimId).toBe(2)
    expect(selectReviewItem(items, 999)?.claimId).toBe(1)
    expect(selectReviewItem([], 999)).toBe(null)
  })
})
