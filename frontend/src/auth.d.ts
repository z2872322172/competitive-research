export type WorkspaceMembership = {
  workspace_id: string
  role: string
}

export type AuthUser = {
  id: number
  username: string
  display_name: string
  is_active: boolean
  workspaces: WorkspaceMembership[]
}

export type AuthSession = {
  token: string
  user: AuthUser
}

export function loadAuthSession(): AuthSession | null
export function saveAuthSession(session: AuthSession): void
export function clearAuthSession(): void
export function authHeaders(): Record<string, string>
export function activeWorkspaceId(): string | null
export function isUnauthorizedError(error: unknown): boolean
