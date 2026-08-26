import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  buildEvidenceQuery,
  buildEvidenceViewModel,
  buildEvidenceWallItems,
  buildEvidenceTraceState,
  filterEvidenceViewModels,
  snapshotPreviewText,
} from './researchEvidence.js'

test('buildEvidenceViewModel exposes source traceability fields', () => {
  const evidence = buildEvidenceViewModel(
    {
      id: 'evidence-1',
      source_id: 'source-1',
      quote: 'Business plan includes privacy controls.',
      locator: { css_selector: '#pricing', paragraph_index: 3 },
      extraction_method: 'trafilatura',
      language: 'en',
      quality_score: 0.83,
      source: {
        id: 'source-1',
        task_id: 'task-1',
        url: 'https://example.com/pricing',
        canonical_url: 'https://example.com/pricing?canonical=1',
        source_type: 'official',
        title: 'Pricing',
        publisher: 'Example',
        published_at: null,
        retrieved_at: '2026-08-14T10:00:00Z',
        content_hash: 'hash',
        index_status: 'indexed',
      },
    },
    2,
  )

  assert.equal(evidence.id, 'evidence-1')
  assert.equal(evidence.sourceId, 'source-1')
  assert.equal(evidence.type, '官方')
  assert.equal(evidence.sourceUrl, 'https://example.com/pricing')
  assert.equal(evidence.canonicalUrl, 'https://example.com/pricing?canonical=1')
  assert.equal(evidence.locatorText, 'css_selector: #pricing · paragraph_index: 3')
  assert.equal(evidence.extractionMethod, 'trafilatura')
  assert.equal(evidence.claims, 2)
})

test('buildEvidenceWallItems exposes bound claim details for evidence drilldown', () => {
  const [item] = buildEvidenceWallItems(
    [
      buildEvidenceViewModel(
        {
          id: 'evidence-bound',
          source_id: 'source-1',
          quote: 'Pricing evidence',
          locator: {},
          extraction_method: 'trafilatura',
          language: 'en',
          quality_score: 0.91,
          source: {
            source_type: 'official',
            title: 'Pricing',
            publisher: 'Example',
            url: 'https://example.com',
            canonical_url: 'https://example.com',
            retrieved_at: null,
            published_at: null,
          },
        },
        1,
      ),
    ],
    [
      {
        id: 'claim-bound',
        subject: 'Cursor',
        dimension: 'pricing',
        display_text: 'Cursor Business includes privacy mode.',
        status: 'verified',
        evidence_ids: ['evidence-bound'],
      },
    ],
  )

  assert.deepEqual(item.boundClaims, [
    {
      id: 'claim-bound',
      label: 'Cursor / pricing',
      title: 'Cursor Business includes privacy mode.',
      status: 'verified',
    },
  ])
})

test('snapshotPreviewText prefers available summaries and keeps unavailable states stable', () => {
  assert.equal(
    snapshotPreviewText(
      {
        source_id: 'source-1',
        artifact_type: 'html_snapshot',
        available: true,
        content_hash: 'hash',
        object_key: 'snapshots/source-1.html',
        summary: 'Pricing page summary',
        char_count: 120,
      },
      '内容哈希 hash',
    ),
    'Pricing page summary',
  )
  assert.equal(
    snapshotPreviewText(
      {
        source_id: 'source-1',
        artifact_type: 'html_snapshot',
        available: false,
        content_hash: 'hash',
        object_key: 'snapshots/source-1.html',
        summary: '',
        char_count: 0,
      },
      '内容哈希 hash',
    ),
    '快照暂不可用 · 内容哈希 hash',
  )
})

test('buildEvidenceTraceState combines source and snapshot states for evidence drilldown', () => {
  const evidence = {
    id: 'ev-1',
    sourceId: 'src-1',
    sourceUrl: '',
    canonicalUrl: 'https://example.com/canonical',
    snapshotHint: 'content hash abc',
  }

  assert.deepEqual(buildEvidenceTraceState(evidence, null, { loading: true }), {
    sourceUrl: 'https://example.com/canonical',
    canOpenSource: true,
    canLoadSnapshot: false,
    snapshotStatus: 'loading',
    snapshotText: '快照读取中...',
  })

  assert.deepEqual(buildEvidenceTraceState(evidence, null, { error: 'not found' }), {
    sourceUrl: 'https://example.com/canonical',
    canOpenSource: true,
    canLoadSnapshot: true,
    snapshotStatus: 'error',
    snapshotText: '快照读取失败：not found',
  })

  assert.deepEqual(
    buildEvidenceTraceState(
      evidence,
      {
        source_id: 'src-1',
        artifact_type: 'html_snapshot',
        available: true,
        content_hash: 'abc',
        object_key: 'snapshots/src-1.html',
        summary: 'Snapshot summary',
        char_count: 42,
      },
      {},
    ),
    {
      sourceUrl: 'https://example.com/canonical',
      canOpenSource: true,
      canLoadSnapshot: true,
      snapshotStatus: 'available',
      snapshotText: 'Snapshot summary',
    },
  )
})

test('buildEvidenceQuery serializes active evidence filters', () => {
  const query = buildEvidenceQuery({
    competitor: 'Cursor',
    dimension: 'pricing',
    sourceType: 'official',
  })

  assert.equal(query, 'evidence_competitor=Cursor&evidence_dimension=pricing&evidence_source_type=official')
  assert.equal(buildEvidenceQuery({ competitor: 'all', dimension: '', sourceType: 'all' }), '')
})

test('filterEvidenceViewModels narrows fallback evidence by source type', () => {
  const items = [
    { id: 'one', sourceType: 'official', type: '瀹樻柟' },
    { id: 'two', sourceType: 'news', type: '鏂伴椈' },
  ]

  assert.deepEqual(filterEvidenceViewModels(items, { sourceType: 'official' }).map((item) => item.id), ['one'])
  assert.deepEqual(filterEvidenceViewModels(items, { sourceType: 'all' }).map((item) => item.id), ['one', 'two'])
})

test('buildEvidenceWallItems attaches claim tags and supports all wall filters', () => {
  const items = buildEvidenceWallItems(
    [
      {
        ...buildEvidenceViewModel(
          {
            id: 'evidence-1',
            source_id: 'source-1',
            quote: 'Pricing evidence',
            locator: {},
            extraction_method: 'trafilatura',
            language: 'en',
            quality_score: 0.91,
            source: {
              source_type: 'official',
              title: 'Pricing',
              publisher: 'Example',
              url: 'https://example.com',
              canonical_url: 'https://example.com',
              retrieved_at: null,
              published_at: null,
            },
          },
          1,
        ),
      },
    ],
    [
      {
        id: 'claim-1',
        subject: 'Cursor',
        dimension: '定价策略',
        evidence_ids: ['evidence-1'],
      },
    ],
  )

  assert.deepEqual(items[0].competitors, ['Cursor'])
  assert.deepEqual(items[0].dimensions, ['定价策略'])
  assert.equal(items[0].qualityTone, 'high')
  assert.equal(filterEvidenceViewModels(items, { competitor: 'Cursor' }).length, 1)
  assert.equal(filterEvidenceViewModels(items, { dimension: '定价策略' }).length, 1)
  assert.equal(filterEvidenceViewModels(items, { sourceType: 'news' }).length, 0)
})
