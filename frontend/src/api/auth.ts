import { request } from './client'
import type { AuthTokenResponse, AuthUser } from './types'
import type { AuthSession } from '@/lib/authSession'

export function apiRegister(username: string, password: string, workspaceId?: string) {
  const body: Record<string, string> = { username, password }
  if (workspaceId) body.workspace_id = workspaceId
  return request<AuthTokenResponse>('/auth/register', { method: 'POST', body: JSON.stringify(body) })
}

export function apiLogin(username: string, password: string) {
  return request<AuthTokenResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
}

export function apiWhoami() {
  return request<AuthUser>('/auth/me')
}

export function buildAuthSession(response: AuthTokenResponse): AuthSession {
  return { token: response.token, user: response.user }
}
