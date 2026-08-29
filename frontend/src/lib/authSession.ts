// 登录态本地存储：JWT 令牌 + 用户信息（含工作区成员关系）。
// localStorage 键名 verda_auth；令牌过期/失效时由 api 层抛出 ApiUnauthorized，
// App 层捕获后清除会话并展示登录面板。
// localStorage 被浏览器禁用（无痕模式/站点数据阻止）时回退到内存会话，
// 保证当前页面内的登录流程依然可用（仅刷新后丢失）。

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

const STORAGE_KEY = 'verda_auth'

// 内存回退会话：仅当 localStorage 不可用时使用。
let memorySession: AuthSession | null = null

// 非浏览器环境（node --test）没有 localStorage，视为无登录态。
function localStorageAvailable(): boolean {
  return typeof window !== 'undefined' && !!window.localStorage
}

export function loadAuthSession(): AuthSession | null {
  if (memorySession) return memorySession
  if (!localStorageAvailable()) return null
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as AuthSession
    if (!parsed?.token || !parsed?.user?.username) return null
    return parsed
  } catch {
    return null
  }
}

export function saveAuthSession(session: AuthSession): void {
  memorySession = session
  if (!localStorageAvailable()) return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
  } catch {
    // 配额满/隐私策略拦截时静默降级为内存会话。
  }
}

export function clearAuthSession(): void {
  memorySession = null
  if (!localStorageAvailable()) return
  try {
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {
    // 同上：静默降级。
  }
}

export function authHeaders(): Record<string, string> {
  const session = loadAuthSession()
  return session ? { Authorization: `Bearer ${session.token}` } : {}
}

export function activeWorkspaceId(): string | null {
  return loadAuthSession()?.user.workspaces[0]?.workspace_id ?? null
}

export function isUnauthorizedError(error: unknown): boolean {
  return typeof error === 'object' && error !== null && 'status' in error && (error as { status: unknown }).status === 401
}
