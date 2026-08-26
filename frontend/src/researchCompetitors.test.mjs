import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  buildCompetitorReuseItems,
  buildCompetitorRows,
  buildScopedRequestHeaders,
  resolveWorkspaceId,
} from './researchCompetitors.js'

const fallbackRows = [
  { name: 'Fallback', category: 'Demo', reports: 1, verified: 2, conflicts: 0, update: 'demo row' },
]

test('buildCompetitorRows converts profiles into competitor table rows', () => {
  const rows = buildCompetitorRows(
    [
      {
        name: 'Cursor',
        category: 'AI code editor',
        task_count: 2,
        verified_claim_count: 5,
        risky_claim_count: 1,
        report_count: 3,
        source_count: 2,
        updated_at: '2026-08-16T11:30:00Z',
      },
    ],
    fallbackRows,
  )

  assert.equal(rows.length, 1)
  assert.equal(rows[0].name, 'Cursor')
  assert.equal(rows[0].category, 'AI code editor')
  assert.equal(rows[0].reports, 3)
  assert.equal(rows[0].verified, 5)
  assert.equal(rows[0].conflicts, 1)
  assert.equal(rows[0].sourceCount, 2)
  assert.match(rows[0].update, /2 个常用来源/)
})

test('buildCompetitorRows falls back when profiles are empty', () => {
  assert.deepEqual(buildCompetitorRows([], fallbackRows), fallbackRows)
})

test('buildCompetitorReuseItems summarizes reused profile sources', () => {
  const items = buildCompetitorReuseItems({
    competitor_profile_reuse: [
      {
        profile_id: 'comp-1',
        name: 'Cursor',
        source_count: 2,
        source_urls: [
          { label: 'Pricing', url: 'https://cursor.com/pricing', source_type: 'official' },
          { label: 'Docs', url: 'https://docs.cursor.com', source_type: 'docs' },
        ],
      },
    ],
  })

  assert.equal(items.length, 1)
  assert.equal(items[0].id, 'comp-1')
  assert.equal(items[0].name, 'Cursor')
  assert.equal(items[0].sourceCountLabel, '2 个来源')
  assert.equal(items[0].sourceLabels, 'Pricing, Docs')
})

test('buildCompetitorReuseItems returns empty rows for missing or invalid scope', () => {
  assert.deepEqual(buildCompetitorReuseItems({}), [])
  assert.deepEqual(buildCompetitorReuseItems({ competitor_profile_reuse: {} }), [])
})

test('resolveWorkspaceId prefers explicit workspace and falls back to configured default', () => {
  assert.equal(resolveWorkspaceId('team-a', 'default'), 'team-a')
  assert.equal(resolveWorkspaceId('', 'workspace-from-env'), 'workspace-from-env')
  assert.equal(resolveWorkspaceId('', ''), 'default')
})

test('buildScopedRequestHeaders preserves custom headers and adds workspace and user headers', () => {
  const headers = buildScopedRequestHeaders(
    {
      Accept: 'application/pdf',
    },
    {
      workspaceId: 'workspace-a',
      userId: 'user-a',
    },
  )

  assert.equal(headers.Accept, 'application/pdf')
  assert.equal(headers['X-Workspace-Id'], 'workspace-a')
  assert.equal(headers['X-User-Id'], 'user-a')
})

test('buildScopedRequestHeaders does not override explicit workspace or user headers', () => {
  const headers = buildScopedRequestHeaders(
    {
      'X-Workspace-Id': 'workspace-explicit',
      'X-User-Id': 'user-explicit',
    },
    {
      workspaceId: 'workspace-default',
      userId: 'user-default',
    },
  )

  assert.equal(headers['X-Workspace-Id'], 'workspace-explicit')
  assert.equal(headers['X-User-Id'], 'user-explicit')
})
