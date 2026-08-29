import { buildScopedRequestHeaders, resolveWorkspaceId } from '@/lib/competitors'
import { authHeaders, activeWorkspaceId, type AuthSession } from '@/lib/authSession'

// 携带登录态的错误：status 为 HTTP 状态码，code 为后端 error.code（如 missing_token）。
export class ApiError extends Error {
  status: number
  code: string

  constructor(message: string, status: number, code: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

type RuntimeProcess = { env?: Record<string, string | undefined> }

const viteEnv = import.meta.env ?? {}
const runtimeEnv = (globalThis as typeof globalThis & { process?: RuntimeProcess }).process?.env ?? {}

export const API_BASE_URL = viteEnv.VITE_API_BASE_URL ?? runtimeEnv.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/v1'
export const DEFAULT_WORKSPACE_ID = viteEnv.VITE_WORKSPACE_ID ?? runtimeEnv.VITE_WORKSPACE_ID
export const DEFAULT_USER_ID = viteEnv.VITE_USER_ID ?? runtimeEnv.VITE_USER_ID

type ApiErrorBody = {
  error?: {
    code?: string
    message?: string
    details?: unknown
  }
}

// 鉴权/工作区头合并：登录态优先（Authorization + 激活工作区），未登录退回环境变量默认值。
// 注意：Authorization 必须合并进最终请求头；此前误将其展开进 scope（第 2 个参数），
// buildScopedRequestHeaders 只读取 scope 的 workspaceId/userId，导致 token 被静默丢弃、
// 登录后所有接口仍返回 401。
function mergedHeaders(headers: HeadersInit | undefined): Record<string, string> {
  const sessionWorkspace = activeWorkspaceId()
  const merged = buildScopedRequestHeaders(headers, {
    workspaceId: sessionWorkspace ?? DEFAULT_WORKSPACE_ID,
    userId: DEFAULT_USER_ID,
  })
  return { ...merged, ...authHeaders() }
}

function toApiError(response: Response, text: string): ApiError {
  try {
    const body = JSON.parse(text) as ApiErrorBody
    return new ApiError(
      body.error?.message || body.error?.code || `API request failed: ${response.status}`,
      response.status,
      body.error?.code || 'http_error',
    )
  } catch {
    return new ApiError(text || `API request failed: ${response.status}`, response.status, 'http_error')
  }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...mergedHeaders(options.headers),
    },
  })

  if (!response.ok) throw toApiError(response, await response.text())

  return response.json() as Promise<T>
}

export async function requestBlob(path: string, options: RequestInit = {}): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: mergedHeaders(options.headers),
  })

  if (!response.ok) throw toApiError(response, await response.text())

  return response.blob()
}

export { resolveWorkspaceId, type AuthSession }
