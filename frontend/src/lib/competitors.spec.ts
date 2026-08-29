import { describe, expect, it } from 'vitest'

import {
  buildCompetitorReuseItems,
  buildCompetitorRows,
  buildScopedRequestHeaders,
  resolveWorkspaceId,
} from './competitors'

const fallbackRows = [
  { name: 'Fallback', category: 'Demo', reports: 1, verified: 2, conflicts: 0, update: 'demo row' },
]

describe('buildCompetitorRows', () => {
  it('converts profiles into competitor table rows', () => {
    const rows = buildCompetitorRows(
      [
        {
          id: 1,
          workspace_id: 'default',
          name: 'Cursor',
          category: 'AI code editor',
          description: '',
          homepage_url: '',
          source_urls: [],
          source_count: 2,
          task_count: 2,
          verified_claim_count: 5,
          risky_claim_count: 1,
          report_count: 3,
          created_at: '2026-08-16T11:30:00Z',
          updated_at: '2026-08-16T11:30:00Z',
        },
      ],
      fallbackRows,
    )

    expect(rows.length).toBe(1)
    expect(rows[0].name).toBe('Cursor')
    expect(rows[0].category).toBe('AI code editor')
    expect(rows[0].reports).toBe(3)
    expect(rows[0].verified).toBe(5)
    expect(rows[0].conflicts).toBe(1)
    expect(rows[0].sourceCount).toBe(2)
    expect(rows[0].update).toMatch(/2 个常用来源/)
  })

  it('falls back when profiles are empty', () => {
    expect(buildCompetitorRows([], fallbackRows)).toEqual(fallbackRows)
  })
})

describe('buildCompetitorReuseItems', () => {
  it('summarizes reused profile sources', () => {
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

    expect(items.length).toBe(1)
    expect(items[0].id).toBe('comp-1')
    expect(items[0].name).toBe('Cursor')
    expect(items[0].sourceCountLabel).toBe('2 个来源')
    expect(items[0].sourceLabels).toBe('Pricing, Docs')
  })

  it('returns empty rows for missing or invalid scope', () => {
    expect(buildCompetitorReuseItems({})).toEqual([])
    expect(buildCompetitorReuseItems({ competitor_profile_reuse: {} })).toEqual([])
  })
})

describe('resolveWorkspaceId', () => {
  it('prefers explicit workspace and falls back to configured default', () => {
    expect(resolveWorkspaceId('team-a', 'default')).toBe('team-a')
    expect(resolveWorkspaceId('', 'workspace-from-env')).toBe('workspace-from-env')
    expect(resolveWorkspaceId('', '')).toBe('default')
  })
})

describe('buildScopedRequestHeaders', () => {
  it('preserves custom headers and adds workspace and user headers', () => {
    const headers = buildScopedRequestHeaders(
      {
        Accept: 'application/pdf',
      },
      {
        workspaceId: 'workspace-a',
        userId: 'user-a',
      },
    )

    expect(headers.Accept).toBe('application/pdf')
    expect(headers['X-Workspace-Id']).toBe('workspace-a')
    expect(headers['X-User-Id']).toBe('user-a')
  })

  it('does not override explicit workspace or user headers', () => {
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

    expect(headers['X-Workspace-Id']).toBe('workspace-explicit')
    expect(headers['X-User-Id']).toBe('user-explicit')
  })
})
