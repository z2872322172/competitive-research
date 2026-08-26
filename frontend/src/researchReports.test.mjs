import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  buildPostReviewReportUpdateState,
  buildReportSectionEvidenceItems,
  buildReportVersionItems,
  selectNewestReportVersion,
} from './researchReports.js'

const reports = [
  {
    id: 'report-1',
    version: 1,
    citation_coverage: 0.73,
    input_snapshot: {
      report_generation: {
        reason: 'initial_workflow',
      },
    },
    generated_at: '2026-08-16T09:00:00Z',
  },
  {
    id: 'report-3',
    version: 3,
    citation_coverage: 0.91,
    input_snapshot: {
      report_generation: {
        reason: 'manual_regenerate',
      },
    },
    generated_at: '2026-08-16T09:30:00Z',
  },
  {
    id: 'report-2',
    version: 2,
    citation_coverage: 0.84,
    input_snapshot: {
      report_generation: {
        reason: 'after_review',
      },
    },
    generated_at: null,
  },
]

test('buildReportVersionItems sorts newest first and labels generation reasons', () => {
  const items = buildReportVersionItems(reports)

  assert.deepEqual(
    items.map((item) => item.version),
    [3, 2, 1],
  )
  assert.equal(items[0].label, 'v3')
  assert.equal(items[0].reasonLabel, '手动再生成')
  assert.equal(items[0].coveragePercent, 91)
  assert.equal(items[1].reasonLabel, '审核后生成')
  assert.equal(items[1].generatedAtLabel, '生成时间未知')
  assert.equal(items[2].reasonLabel, '初始生成')
})

test('selectNewestReportVersion returns the highest available version', () => {
  assert.equal(selectNewestReportVersion(reports), 3)
  assert.equal(selectNewestReportVersion([]), null)
})

test('buildReportSectionEvidenceItems prepares stable display rows', () => {
  const section = {
    evidence: [
      {
        id: 'ev-2',
        quote: 'Copilot Business provides organization-level policies.',
        source_title: '',
        publisher: 'GitHub Docs',
        source_url: 'https://docs.github.com/copilot',
        quality_score: 0.861,
        relation: 'supports',
        claim_ids: ['claim-2', 'claim-1'],
      },
      {
        id: 'ev-1',
        quote: 'Business plan includes privacy mode.',
        source_title: 'Cursor Pricing',
        publisher: 'Cursor',
        source_url: 'https://cursor.com/pricing',
        quality_score: 0.9,
        relation: 'context',
        claim_ids: ['claim-1'],
      },
    ],
  }

  const items = buildReportSectionEvidenceItems(section)

  assert.deepEqual(
    items.map((item) => item.id),
    ['ev-1', 'ev-2'],
  )
  assert.equal(items[0].sourceLabel, 'Cursor Pricing')
  assert.equal(items[0].qualityLabel, '90%')
  assert.equal(items[0].claimLabel, '1 Claim')
  assert.equal(items[1].sourceLabel, 'GitHub Docs')
  assert.equal(items[1].qualityLabel, '86%')
  assert.equal(items[1].claimLabel, '2 Claims')
  assert.equal(buildReportSectionEvidenceItems({}).length, 0)
})

test('buildReportVersionItems marks the newest report version', () => {
  const items = buildReportVersionItems(reports)

  assert.equal(items[0].isLatest, true)
  assert.equal(items[1].isLatest, false)
  assert.equal(items[2].isLatest, false)
})

test('buildPostReviewReportUpdateState highlights the newest after-review report', () => {
  const state = buildPostReviewReportUpdateState(
    [
      {
        id: 'report-1',
        version: 1,
        citation_coverage: 0.72,
        input_snapshot: { report_generation: { reason: 'initial_workflow' } },
        generated_at: '2026-08-16T09:00:00Z',
      },
      {
        id: 'report-2',
        version: 2,
        citation_coverage: 0.91,
        input_snapshot: { report_generation: { reason: 'after_review' } },
        generated_at: '2026-08-16T09:10:00Z',
      },
    ],
    1,
  )

  assert.equal(state.hasPostReviewUpdate, true)
  assert.equal(state.latestVersion, 2)
  assert.equal(state.selectedVersion, 1)
  assert.equal(state.isViewingLatest, false)
  assert.equal(state.message, '审核后已生成 v2 报告，引用覆盖率 91%。')
  assert.equal(state.actionLabel, '查看 v2')
})
test('buildPostReviewReportUpdateState returns a stable empty state', () => {
  assert.deepEqual(buildPostReviewReportUpdateState([]), {
    hasPostReviewUpdate: false,
    latestVersion: null,
    selectedVersion: null,
    isViewingLatest: false,
    message: '',
    actionLabel: '',
  })
})
