import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'

const originalFetch = globalThis.fetch
const originalEnv = {
  VITE_API_BASE_URL: process.env.VITE_API_BASE_URL,
  VITE_WORKSPACE_ID: process.env.VITE_WORKSPACE_ID,
  VITE_USER_ID: process.env.VITE_USER_ID,
}

afterEach(() => {
  globalThis.fetch = originalFetch
  process.env.VITE_API_BASE_URL = originalEnv.VITE_API_BASE_URL
  process.env.VITE_WORKSPACE_ID = originalEnv.VITE_WORKSPACE_ID
  process.env.VITE_USER_ID = originalEnv.VITE_USER_ID
})

test('exportReportArtifact sends scoped headers and returns a blob', async () => {
  process.env.VITE_API_BASE_URL = 'http://example.test/v1'
  process.env.VITE_WORKSPACE_ID = 'workspace-from-env'
  process.env.VITE_USER_ID = 'user-from-env'

  const calls = []
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init })
    return new Response(new Blob(['report-binary']), {
      status: 200,
      headers: { 'Content-Type': 'application/pdf' },
    })
  }

  const { exportReportArtifact } = await import('./api.ts')
  const blob = await exportReportArtifact('report-1', 'pdf')

  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, 'http://example.test/v1/reports/report-1/export?format=pdf')
  assert.equal(calls[0].init.method, 'POST')
  assert.equal(calls[0].init.headers['X-Workspace-Id'], 'workspace-from-env')
  assert.equal(calls[0].init.headers['X-User-Id'], 'user-from-env')
  assert.equal(blob.type, 'application/pdf')
  assert.equal(await blob.text(), 'report-binary')
})

test('exportReportArtifact surfaces json api errors', async () => {
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ error: { code: 'permission_denied', message: 'permission denied' } }), {
      status: 403,
      headers: { 'Content-Type': 'application/json' },
    })

  const { exportReportArtifact } = await import('./api.ts')

  await assert.rejects(exportReportArtifact('report-1', 'docx'), /permission denied/)
})

test('exportReportArtifact falls back to plain text errors', async () => {
  globalThis.fetch = async () => new Response('gateway timeout', { status: 504 })

  const { exportReportArtifact } = await import('./api.ts')

  await assert.rejects(exportReportArtifact('report-1', 'pdf'), /gateway timeout/)
})
