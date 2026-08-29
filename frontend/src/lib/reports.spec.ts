import { describe, expect, it } from 'vitest'

import {
  buildPostReviewReportUpdateState,
  buildReportSectionEvidenceItems,
  buildReportVersionItems,
  parseMarkdownInlines,
  renderMarkdownBlocks,
  selectNewestReportVersion,
} from './reports'
import type { ReportOut } from '@/api/types'

const reports = [
  {
    id: 1,
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
    id: 3,
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
    id: 2,
    version: 2,
    citation_coverage: 0.84,
    input_snapshot: {
      report_generation: {
        reason: 'after_review',
      },
    },
    generated_at: null,
  },
] as unknown as ReportOut[]

describe('renderMarkdownBlocks', () => {
  it('parses paragraphs, bullets, inline styles and trailing evidence citations', () => {
    const blocks = renderMarkdownBlocks(
      '本报告基于任务“调研”生成，模板版本：`stage5-review-v1`。\n\n' +
        '- **高置信度**结论 6 条。 Evidence: 25, 26\n' +
        '- 暂无必须人工处理的风险结论。\n' +
        '- 混合行内 `code` 与 **加粗**。 Evidence: 30\n',
    )

    expect(blocks).toHaveLength(2)
    expect(blocks[0].kind).toBe('paragraph')
    if (blocks[0].kind === 'paragraph') {
      expect(blocks[0].inlines.map((token) => token.kind)).toEqual(['text', 'code', 'text'])
      expect(blocks[0].inlines[1].text).toBe('stage5-review-v1')
      expect(blocks[0].citations).toEqual([])
    }
    expect(blocks[1].kind).toBe('list')
    if (blocks[1].kind === 'list') {
      expect(blocks[1].items).toHaveLength(3)
      const [first, second, third] = blocks[1].items
      expect(first.inlines[0]).toEqual({ kind: 'strong', text: '高置信度' })
      expect(first.inlines[1]).toEqual({ kind: 'text', text: '结论 6 条。' })
      expect(first.citations).toEqual([25, 26])
      expect(second.citations).toEqual([])
      expect(third.inlines.map((token) => token.kind)).toEqual(['text', 'code', 'text', 'strong', 'text'])
      expect(third.citations).toEqual([30])
    }
  })

  it('keeps chinese evidence separators and empty input safe', () => {
    const blocks = renderMarkdownBlocks('- 中文引用行。证据：25、26')
    expect(blocks).toHaveLength(1)
    expect(blocks[0].kind).toBe('list')
    if (blocks[0].kind === 'list') {
      expect(blocks[0].items[0].citations).toEqual([25, 26])
      expect(blocks[0].items[0].inlines[0].text).toBe('中文引用行。')
    }
    expect(renderMarkdownBlocks('')).toEqual([])
  })
})

describe('parseMarkdownInlines', () => {
  it('returns a single text token for plain strings', () => {
    expect(parseMarkdownInlines('普通文本')).toEqual([{ kind: 'text', text: '普通文本' }])
    expect(parseMarkdownInlines('')).toEqual([])
  })
})

describe('buildReportVersionItems', () => {
  it('sorts newest first and labels generation reasons', () => {
    const items = buildReportVersionItems(reports)

    expect(items.map((item) => item.version)).toEqual([3, 2, 1])
    expect(items[0].label).toBe('v3')
    expect(items[0].reasonLabel).toBe('手动再生成')
    expect(items[0].coveragePercent).toBe(91)
    expect(items[1].reasonLabel).toBe('审核后生成')
    expect(items[1].generatedAtLabel).toBe('生成时间未知')
    expect(items[2].reasonLabel).toBe('初始生成')
  })

  it('marks the newest report version', () => {
    const items = buildReportVersionItems(reports)

    expect(items[0].isLatest).toBe(true)
    expect(items[1].isLatest).toBe(false)
    expect(items[2].isLatest).toBe(false)
  })
})

describe('selectNewestReportVersion', () => {
  it('returns the highest available version', () => {
    expect(selectNewestReportVersion(reports)).toBe(3)
    expect(selectNewestReportVersion([])).toBe(null)
  })
})

describe('buildReportSectionEvidenceItems', () => {
  it('prepares stable display rows', () => {
    const section = {
      evidence: [
        {
          id: 2,
          quote: 'Copilot Business provides organization-level policies.',
          source_title: '',
          publisher: 'GitHub Docs',
          source_url: 'https://docs.github.com/copilot',
          quality_score: 0.861,
          relation: 'supports',
          claim_ids: [2, 1],
          source_id: 2,
        },
        {
          id: 1,
          quote: 'Business plan includes privacy mode.',
          source_title: 'Cursor Pricing',
          publisher: 'Cursor',
          source_url: 'https://cursor.com/pricing',
          quality_score: 0.9,
          relation: 'context',
          claim_ids: [1],
          source_id: 1,
        },
      ],
    }

    const items = buildReportSectionEvidenceItems(section)

    expect(items.map((item) => item.id)).toEqual([1, 2])
    expect(items[0].sourceLabel).toBe('Cursor Pricing')
    expect(items[0].qualityLabel).toBe('90%')
    expect(items[0].claimLabel).toBe('1 Claim')
    expect(items[1].sourceLabel).toBe('GitHub Docs')
    expect(items[1].qualityLabel).toBe('86%')
    expect(items[1].claimLabel).toBe('2 Claims')
    expect(buildReportSectionEvidenceItems({}).length).toBe(0)
  })

  it('maps traceability fields and tolerates legacy evidence rows', () => {
    const section = {
      evidence: [
        {
          id: 7,
          quote: 'Cursor business plan includes privacy mode.',
          source_title: 'Cursor Pricing',
          publisher: 'Cursor',
          source_url: 'https://cursor.com/pricing',
          quality_score: 0.9,
          relation: 'supports',
          claim_ids: [1],
          source_id: 3,
          source_type: 'official',
          reliability_score: 0.85,
          reliability_level: 'high',
          reliability_reasons: ['来源类型基准：official', '标记为一手来源'],
          locator: { kind: 'html', heading: 'Pricing', char_start: 120 },
          snapshot_available: true,
          content_hash: 'task-3-hash',
        },
        {
          id: 8,
          quote: 'Legacy row without traceability fields.',
          source_title: 'Old Source',
          publisher: null,
          source_url: '',
          quality_score: 0.5,
          relation: 'supports',
          claim_ids: [],
          source_id: 4,
        },
      ],
    }

    const items = buildReportSectionEvidenceItems(section)

    expect(items[0].sourceType).toBe('official')
    expect(items[0].reliabilityPercent).toBe(85)
    expect(items[0].reliabilityLabel).toBe('高')
    expect(items[0].reliabilityReasons).toHaveLength(2)
    expect(items[0].locatorText).toBe('kind: html · heading: Pricing · char_start: 120')
    expect(items[0].snapshotAvailable).toBe(true)
    expect(items[0].contentHash).toBe('task-3-hash')

    // 旧报告快照缺新字段时保持可用
    expect(items[1].sourceType).toBe('')
    expect(items[1].reliabilityPercent).toBeNull()
    expect(items[1].reliabilityLabel).toBe('')
    expect(items[1].reliabilityReasons).toEqual([])
    expect(items[1].locatorText).toBe('')
    expect(items[1].snapshotAvailable).toBe(false)
    expect(items[1].contentHash).toBe('')
  })
})

describe('buildPostReviewReportUpdateState', () => {
  it('highlights the newest after-review report', () => {
    const state = buildPostReviewReportUpdateState(
      [
        {
          id: 1,
          version: 1,
          citation_coverage: 0.72,
          input_snapshot: { report_generation: { reason: 'initial_workflow' } },
          generated_at: '2026-08-16T09:00:00Z',
        },
        {
          id: 2,
          version: 2,
          citation_coverage: 0.91,
          input_snapshot: { report_generation: { reason: 'after_review' } },
          generated_at: '2026-08-16T09:10:00Z',
        },
      ] as unknown as ReportOut[],
      1,
    )

    expect(state.hasPostReviewUpdate).toBe(true)
    expect(state.latestVersion).toBe(2)
    expect(state.selectedVersion).toBe(1)
    expect(state.isViewingLatest).toBe(false)
    expect(state.message).toBe('审核后已生成 v2 报告，引用覆盖率 91%。')
    expect(state.actionLabel).toBe('查看 v2')
  })

  it('returns a stable empty state', () => {
    expect(buildPostReviewReportUpdateState([])).toEqual({
      hasPostReviewUpdate: false,
      latestVersion: null,
      selectedVersion: null,
      isViewingLatest: false,
      message: '',
      actionLabel: '',
    })
  })
})
