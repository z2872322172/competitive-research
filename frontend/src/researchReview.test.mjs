import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  buildClaimQualitySnapshot,
  buildClaimQualityJudgement,
  buildLowRiskReviewCandidates,
  buildReviewItems,
  resolveReviewReason,
  selectReviewItem,
} from './researchReview.js'

test('buildLowRiskReviewCandidates returns only safe unreviewed verified claims', () => {
  const candidates = buildLowRiskReviewCandidates([
    {
      id: 'safe',
      status: 'verified',
      confidence_score: 0.86,
      evidence_coverage: 0.91,
      include_in_report: true,
      evidence_ids: ['ev-1'],
      review_decision: null,
    },
    {
      id: 'continue-safe',
      status: 'verified',
      confidence_score: 0.8,
      evidence_coverage: 0.8,
      include_in_report: true,
      evidence_ids: ['ev-1'],
      review_decision: 'continue_research',
    },
    {
      id: 'conflict',
      status: 'conflict',
      confidence_score: 0.95,
      evidence_coverage: 1,
      include_in_report: true,
      evidence_ids: ['ev-1'],
      review_decision: null,
    },
    {
      id: 'excluded',
      status: 'verified',
      confidence_score: 0.95,
      evidence_coverage: 1,
      include_in_report: false,
      evidence_ids: ['ev-1'],
      review_decision: null,
    },
    {
      id: 'accepted',
      status: 'verified',
      confidence_score: 0.95,
      evidence_coverage: 1,
      include_in_report: true,
      evidence_ids: ['ev-1'],
      review_decision: 'accept',
    },
    {
      id: 'weak',
      status: 'verified',
      confidence_score: 0.79,
      evidence_coverage: 1,
      include_in_report: true,
      evidence_ids: ['ev-1'],
      review_decision: null,
    },
    {
      id: 'no-evidence',
      status: 'verified',
      confidence_score: 0.95,
      evidence_coverage: 1,
      include_in_report: true,
      evidence_ids: [],
      review_decision: null,
    },
  ])

  assert.deepEqual(candidates.map((item) => item.claimId), ['safe', 'continue-safe'])
  assert.equal(candidates[0].reason, '批量接受：低风险 Claim 已达到置信度和引用覆盖率阈值。')
})

const evidences = [
  {
    id: 'ev-1',
    sourceType: 'official',
    type: '官方',
    title: 'Cursor Pricing',
    domain: 'cursor.com/pricing',
    confidence: 86,
    excerpt: 'Business plan includes privacy controls.',
  },
  {
    id: 'ev-2',
    sourceType: 'news',
    type: '新闻',
    title: 'Market Update',
    domain: 'news.example',
    confidence: 54,
    excerpt: 'Older market article cites a different price.',
  },
]

test('buildReviewItems adds quality context and bound evidence summaries', () => {
  const items = buildReviewItems(
    [
      {
        id: 'claim-1',
        status: 'conflict',
        confidence_score: 0.62,
        evidence_coverage: 0.5,
        display_text: 'Cursor price conflicts across sources.',
        evidence_ids: ['ev-1', 'ev-2'],
        review_decision: null,
      },
      {
        id: 'claim-2',
        status: 'verified',
        confidence_score: 0.95,
        evidence_coverage: 1,
        display_text: 'Already verified claim.',
        evidence_ids: ['ev-1'],
        review_decision: 'accept',
      },
    ],
    evidences,
  )

  assert.equal(items.length, 1)
  assert.equal(items[0].claimId, 'claim-1')
  assert.equal(items[0].kind, '冲突')
  assert.equal(items[0].statusLabel, '存在冲突')
  assert.equal(items[0].confidencePercent, 62)
  assert.equal(items[0].coveragePercent, 50)
  assert.deepEqual(
    items[0].evidenceSummaries.map((item) => item.label),
    ['ev-1 · 官方 · 86% · Cursor Pricing', 'ev-2 · 新闻 · 54% · Market Update'],
  )
})

test('buildClaimQualitySnapshot exposes confidence, coverage and evidence bindings', () => {
  const snapshot = buildClaimQualitySnapshot(
    {
      id: 'claim-1',
      status: 'conflict',
      confidence_score: 0.62,
      evidence_coverage: 0.5,
      evidence_ids: ['ev-1', 'ev-2'],
    },
    [
      {
        id: 'ev-1',
        type: '官方',
        confidence: 86,
        title: 'Cursor Pricing',
      },
      {
        id: 'ev-2',
        type: '新闻',
        confidence: 54,
        title: 'Market Update',
      },
    ],
  )

  assert.equal(snapshot.confidencePercent, 62)
  assert.equal(snapshot.coveragePercent, 50)
  assert.equal(snapshot.statusLabel, '存在冲突')
  assert.deepEqual(
    snapshot.evidenceSummaries.map((item) => item.label),
    ['ev-1 · 官方 · 86% · Cursor Pricing', 'ev-2 · 新闻 · 54% · Market Update'],
  )
})

test('buildClaimQualityJudgement summarizes confidence, coverage, conflict state and evidence bindings', () => {
  const judgement = buildClaimQualityJudgement(
    {
      id: 'claim-risk',
      status: 'conflict',
      confidence: 'conflict',
      confidence_score: 0.57,
      evidence_coverage: 0.5,
      evidence_ids: ['ev-1', 'ev-2'],
    },
    evidences,
  )

  assert.equal(judgement.riskLevel, 'high')
  assert.equal(judgement.confidenceText, '57% · 冲突')
  assert.equal(judgement.coverageText, '50%')
  assert.equal(judgement.statusText, '存在冲突')
  assert.equal(judgement.evidenceText, '2 条 Evidence')
  assert.deepEqual(judgement.flags, ['conflict', 'low_confidence', 'partial_coverage'])
  assert.deepEqual(judgement.flagLabels, ['存在冲突', '低置信度', '覆盖不足'])
  assert.deepEqual(
    judgement.evidenceSummaries.map((item) => item.id),
    ['ev-1', 'ev-2'],
  )
})

test('buildReviewItems keeps continue research claims visible for another decision', () => {
  const items = buildReviewItems(
    [
      {
        id: 'claim-continue',
        status: 'needs_evidence',
        confidence_score: 0.31,
        evidence_coverage: 0,
        display_text: 'Needs more evidence.',
        evidence_ids: [],
        review_decision: 'continue_research',
      },
    ],
    evidences,
  )

  assert.equal(items.length, 1)
  assert.equal(items[0].claimId, 'claim-continue')
  assert.equal(items[0].kind, '低置信度')
  assert.equal(items[0].evidenceSummaries[0].label, '暂无绑定证据')
})

test('resolveReviewReason prefers typed reviewer reason and falls back to recommendation', () => {
  const item = {
    recommendation: '优先采用官方来源。',
  }

  assert.equal(resolveReviewReason(item, '  官网更可信 '), '官网更可信')
  assert.equal(resolveReviewReason(item, '   '), '优先采用官方来源。')
})

test('selectReviewItem returns the requested item or the first visible item', () => {
  const items = [
    { claimId: 'claim-1', title: 'First review item' },
    { claimId: 'claim-2', title: 'Second review item' },
  ]

  assert.equal(selectReviewItem(items, 'claim-2').claimId, 'claim-2')
  assert.equal(selectReviewItem(items, 'missing').claimId, 'claim-1')
  assert.equal(selectReviewItem([], 'missing'), null)
})

test('buildReviewItems exposes confidence labels for the review panel', () => {
  const items = buildReviewItems(
    [
      {
        id: 'claim-confidence',
        status: 'conflict',
        confidence: 'low',
        confidence_score: 0.74,
        evidence_coverage: 0.88,
        display_text: 'Confidence label should be visible.',
        evidence_ids: ['ev-1'],
        review_decision: null,
      },
    ],
    evidences,
  )

  assert.equal(items[0].confidenceLabel, '低')
})

test('buildReviewItems keeps reviewer reasons on visible continue-research claims', () => {
  const items = buildReviewItems(
    [
      {
        id: 'claim-continue-reason',
        status: 'needs_evidence',
        confidence: 'low',
        confidence_score: 0.42,
        evidence_coverage: 0.25,
        display_text: 'Needs more primary evidence.',
        evidence_ids: [],
        review_decision: 'continue_research',
        review_reason: 'Need one official pricing source.',
        reviewed_at: '2026-08-23T10:00:00Z',
      },
    ],
    evidences,
  )

  assert.equal(items[0].reviewReason, 'Need one official pricing source.')
  assert.equal(items[0].reviewedAt, '2026-08-23T10:00:00Z')
})
