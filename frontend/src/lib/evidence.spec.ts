import { describe, expect, it } from 'vitest'

import {
  buildEvidenceFilterOptions,
  buildEvidenceQuery,
  buildEvidenceViewModel,
  buildEvidenceWallItems,
  buildEvidenceTraceState,
  filterEvidenceViewModels,
  snapshotPreviewText,
  type EvidenceViewModel,
} from './evidence'
import type { EvidenceOut } from '@/api/types'

describe('buildEvidenceViewModel', () => {
  it('exposes source traceability fields', () => {
    const evidence = buildEvidenceViewModel(
      {
        id: 1,
        source_id: 1,
        quote: 'Business plan includes privacy controls.',
        locator: { css_selector: '#pricing', paragraph_index: 3 },
        extraction_method: 'trafilatura',
        language: 'en',
        quality_score: 0.83,
        source: {
          id: 1,
          task_id: 1,
          url: 'https://example.com/pricing',
          canonical_url: 'https://example.com/pricing?canonical=1',
          source_type: 'official',
          title: 'Pricing',
          publisher: 'Example',
          published_at: null,
          retrieved_at: '2026-08-14T10:00:00Z',
          content_hash: 'hash',
          index_status: 'indexed',
          reliability: {
            score: 0.92,
            label: 'high',
            reasons: ['标记为一手来源', '已保存内容哈希，可追溯快照'],
            warnings: [],
          },
        },
      } as EvidenceOut,
      2,
    )

    expect(evidence.id).toBe(1)
    expect(evidence.sourceId).toBe(1)
    expect(evidence.type).toBe('官方')
    expect(evidence.sourceUrl).toBe('https://example.com/pricing')
    expect(evidence.canonicalUrl).toBe('https://example.com/pricing?canonical=1')
    expect(evidence.locatorText).toBe('css_selector: #pricing · paragraph_index: 3')
    expect(evidence.extractionMethod).toBe('trafilatura')
    expect(evidence.claims).toBe(2)
    expect(evidence.reliabilityScore).toBe(92)
    expect(evidence.reliabilityReasons).toContain('标记为一手来源')
  })
})

describe('buildEvidenceWallItems', () => {
  it('exposes bound claim details for evidence drilldown', () => {
    const [item] = buildEvidenceWallItems(
      [
        buildEvidenceViewModel(
          {
            id: 2,
            source_id: 1,
            quote: 'Pricing evidence',
            locator: {},
            extraction_method: 'trafilatura',
            language: 'en',
            quality_score: 0.91,
            source: {
              id: 1,
              task_id: 1,
              url: 'https://example.com/pricing',
              canonical_url: 'https://example.com/pricing',
              source_type: 'official',
              title: 'Pricing',
              publisher: 'Example',
              published_at: null,
              retrieved_at: '2026-08-16T11:30:00Z',
              content_hash: 'abc123',
              index_status: 'completed',
            },
          } as EvidenceOut,
          1,
        ),
      ],
      [
        {
          id: 2,
          subject: 'Cursor',
          dimension: 'pricing',
          display_text: 'Cursor Business includes privacy mode.',
          status: 'verified',
          evidence_ids: [2],
        },
      ],
    )

    expect(item.boundClaims).toEqual([
      {
        id: 2,
        label: 'Cursor / pricing',
        title: 'Cursor Business includes privacy mode.',
        status: 'verified',
      },
    ])
  })

  it('attaches claim tags and supports all wall filters', () => {
    const items = buildEvidenceWallItems(
      [
        {
          ...buildEvidenceViewModel(
            {
              id: 1,
              source_id: 1,
              quote: 'Pricing evidence',
              locator: {},
              extraction_method: 'trafilatura',
              language: 'en',
              quality_score: 0.91,
              source: {
                id: 1,
                task_id: 1,
                source_type: 'official',
                title: 'Pricing',
                publisher: 'Example',
                url: 'https://example.com',
                canonical_url: 'https://example.com',
                retrieved_at: '2026-08-16T11:30:00Z',
                published_at: null,
                content_hash: 'abc',
                index_status: 'completed',
              },
            } as EvidenceOut,
            1,
          ),
        },
      ],
      [
        {
          id: 1,
          subject: 'Cursor',
          dimension: '定价策略',
          evidence_ids: [1],
        },
      ],
    )

    expect(items[0].competitors).toEqual(['Cursor'])
    expect(items[0].dimensions).toEqual(['定价策略'])
    expect(items[0].qualityTone).toBe('high')
    expect(filterEvidenceViewModels(items, { competitor: 'Cursor' }).length).toBe(1)
    expect(filterEvidenceViewModels(items, { dimension: '定价策略' }).length).toBe(1)
    expect(filterEvidenceViewModels(items, { sourceType: 'news' }).length).toBe(0)
  })
})

describe('snapshotPreviewText', () => {
  it('prefers available summaries and keeps unavailable states stable', () => {
    expect(
      snapshotPreviewText(
        {
          source_id: 1,
          artifact_type: 'html_snapshot',
          available: true,
          content_hash: 'hash',
          object_key: 'snapshots/1.html',
          summary: 'Pricing page summary',
          char_count: 120,
        },
        '内容哈希 hash',
      ),
    ).toBe('Pricing page summary')
    expect(
      snapshotPreviewText(
        {
          source_id: 1,
          artifact_type: 'html_snapshot',
          available: false,
          content_hash: 'hash',
          object_key: 'snapshots/1.html',
          summary: '',
          char_count: 0,
        },
        '内容哈希 hash',
      ),
    ).toBe('快照暂不可用 · 内容哈希 hash')
  })
})

describe('buildEvidenceTraceState', () => {
  it('combines source and snapshot states for evidence drilldown', () => {
    const evidence = {
      id: 1,
      sourceId: 1,
      sourceUrl: '',
      canonicalUrl: 'https://example.com/canonical',
      snapshotHint: 'content hash abc',
    }

    expect(buildEvidenceTraceState(evidence, null, { loading: true })).toEqual({
      sourceUrl: 'https://example.com/canonical',
      canOpenSource: true,
      canLoadSnapshot: false,
      snapshotStatus: 'loading',
      snapshotText: '快照读取中...',
    })

    expect(buildEvidenceTraceState(evidence, null, { error: 'not found' })).toEqual({
      sourceUrl: 'https://example.com/canonical',
      canOpenSource: true,
      canLoadSnapshot: true,
      snapshotStatus: 'error',
      snapshotText: '快照读取失败：not found',
    })

    expect(
      buildEvidenceTraceState(
        evidence,
        {
          source_id: 1,
          artifact_type: 'html_snapshot',
          available: true,
          content_hash: 'abc',
          object_key: 'snapshots/1.html',
          summary: 'Snapshot summary',
          char_count: 42,
        },
        {},
      ),
    ).toEqual({
      sourceUrl: 'https://example.com/canonical',
      canOpenSource: true,
      canLoadSnapshot: true,
      snapshotStatus: 'available',
      snapshotText: 'Snapshot summary',
    })
  })
})

describe('buildEvidenceQuery', () => {
  it('serializes active evidence filters', () => {
    const query = buildEvidenceQuery({
      competitor: 'Cursor',
      dimension: 'pricing',
      sourceType: 'official',
    })

    expect(query).toBe('evidence_competitor=Cursor&evidence_dimension=pricing&evidence_source_type=official')
    expect(buildEvidenceQuery({ competitor: 'all', dimension: '', sourceType: 'all' })).toBe('')
  })
})

describe('filterEvidenceViewModels', () => {
  it('narrows fallback evidence by source type', () => {
    const items = [
      { id: 1, sourceType: 'official', type: '官方' },
      { id: 2, sourceType: 'news', type: '新闻' },
    ]

    expect(filterEvidenceViewModels(items as EvidenceViewModel[], { sourceType: 'official' }).map((item) => item.id)).toEqual([1])
    expect(filterEvidenceViewModels(items as EvidenceViewModel[], { sourceType: 'all' }).map((item) => item.id)).toEqual([1, 2])
  })
})

describe('buildEvidenceFilterOptions', () => {
  it('derives options from the complete wall list so active filters cannot hide choices', () => {
    const options = buildEvidenceFilterOptions([
      { sourceType: 'news', competitors: ['Trae'], dimensions: ['用户口碑'] },
      { sourceType: 'official', competitors: ['Cursor', 'Trae'], dimensions: ['定价策略'] },
      { sourceType: 'official', competitors: ['Cursor'], dimensions: ['定价策略'] },
    ])

    expect(options.sourceTypes).toEqual(['news', 'official'])
    expect(options.competitors).toEqual(['Cursor', 'Trae'])
    expect(options.dimensions).toEqual(['定价策略', '用户口碑'])
  })
})
