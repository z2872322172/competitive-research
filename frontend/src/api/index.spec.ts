import { afterEach, describe, expect, it, vi } from 'vitest'

import { exportReportArtifact, getResearchTask, listResearchTasks, createResearchTask } from './index'

const originalFetch = globalThis.fetch

afterEach(() => {
  globalThis.fetch = originalFetch
  vi.unstubAllEnvs()
})

describe('exportReportArtifact', () => {
  it('sends scoped headers and returns a blob', async () => {
    // API_BASE_URL 在模块加载时读取环境变量，stub 后需重新加载模块。
    vi.resetModules()
    vi.stubEnv('VITE_API_BASE_URL', 'http://example.test/v1')
    vi.stubEnv('VITE_WORKSPACE_ID', 'workspace-from-env')
    vi.stubEnv('VITE_USER_ID', 'user-from-env')

    const calls: Array<{ url: string; init: RequestInit }> = []
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), init: init ?? {} })
      return new Response(new Blob(['report-binary']), {
        status: 200,
        headers: { 'Content-Type': 'application/pdf' },
      })
    }) as typeof fetch

    const { exportReportArtifact: exportArtifact } = await import('./index')
    const blob = await exportArtifact(1, 'pdf')

    expect(calls.length).toBe(1)
    expect(calls[0].url).toBe('http://example.test/v1/reports/1/export?format=pdf')
    expect(calls[0].init.method).toBe('POST')
    expect((calls[0].init.headers as Record<string, string>)['X-Workspace-Id']).toBe('workspace-from-env')
    expect((calls[0].init.headers as Record<string, string>)['X-User-Id']).toBe('user-from-env')
    expect(blob.type).toBe('application/pdf')
    expect(await blob.text()).toBe('report-binary')
  })

  it('surfaces json api errors', async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ error: { code: 'permission_denied', message: 'permission denied' } }), {
          status: 403,
          headers: { 'Content-Type': 'application/json' },
        }),
    )

    await expect(exportReportArtifact(1, 'docx')).rejects.toThrow(/permission denied/)
  })

  it('falls back to plain text errors', async () => {
    globalThis.fetch = vi.fn(async () => new Response('gateway timeout', { status: 504 }))

    await expect(exportReportArtifact(1, 'pdf')).rejects.toThrow(/gateway timeout/)
  })
})

describe('request error handling', () => {
  it('sends the Authorization header when a session exists', async () => {
    // 回归：Authorization 曾被误并入 scope 而丢弃，导致登录后所有接口 401。
    vi.resetModules()
    vi.stubEnv('VITE_API_BASE_URL', 'http://example.test/v1')

    const { saveAuthSession } = await import('../lib/authSession')
    saveAuthSession({
      token: 'jwt-token',
      user: {
        id: 1,
        username: 'probe_test',
        display_name: '',
        is_active: true,
        workspaces: [{ workspace_id: 'ws-1', role: 'owner' }],
      },
    })

    const calls: Array<{ url: string; init: RequestInit }> = []
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: String(input), init: init ?? {} })
      return new Response(JSON.stringify([]), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }) as typeof fetch

    const { listResearchTasks: list } = await import('./index')
    await list()

    const headers = calls[0].init.headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer jwt-token')
    expect(headers['X-Workspace-Id']).toBe('ws-1')
  })

  it('surfaces network failures as errors', async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new TypeError('Failed to fetch')
    })

    await expect(getResearchTask(1)).rejects.toThrow(/Failed to fetch/)
  })

  it('falls back to status text when the error body is empty', async () => {
    globalThis.fetch = vi.fn(async () => new Response('', { status: 500 }))

    await expect(listResearchTasks()).rejects.toThrow(/API request failed: 500/)
  })

  it('prefers the api error code when message is missing', async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ error: { code: 'validation_error' } }), {
          status: 422,
          headers: { 'Content-Type': 'application/json' },
        }),
    )

    await expect(createResearchTask({ prompt: '', competitors: [], dimensions: [], source_preferences: [], report_depth: 'standard', time_range: 'last_12_months', output_format: 'comprehensive_report' })).rejects.toThrow(/validation_error/)
  })

  it('surfaces fastapi validation errors without detail message', async () => {
    globalThis.fetch = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: 'prompt must not be empty' }), {
          status: 422,
          headers: { 'Content-Type': 'application/json' },
        }),
    )

    await expect(createResearchTask({ prompt: '', competitors: [], dimensions: [], source_preferences: [], report_depth: 'standard', time_range: 'last_12_months', output_format: 'comprehensive_report' })).rejects.toThrow(/API request failed: 422/)
  })
})
