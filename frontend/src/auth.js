// 登录态本地存储：JWT 令牌 + 用户信息（含工作区成员关系）。
// localStorage 键名 verda_auth；令牌过期/失效时由 api 层抛出 ApiUnauthorized，
// App 层捕获后清除会话并展示登录面板。

const STORAGE_KEY = 'verda_auth'

// 非浏览器环境（node --test）没有 localStorage，视为无登录态。
function localStorageAvailable() {
  return typeof window !== 'undefined' && !!window.localStorage
}

export function loadAuthSession() {
  if (!localStorageAvailable()) return null
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed?.token || !parsed?.user?.username) return null
    return parsed
  } catch {
    return null
  }
}

export function saveAuthSession(session) {
  if (!localStorageAvailable()) return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session))
}

export function clearAuthSession() {
  if (!localStorageAvailable()) return
  window.localStorage.removeItem(STORAGE_KEY)
}

export function authHeaders() {
  const session = loadAuthSession()
  return session ? { Authorization: `Bearer ${session.token}` } : {}
}

export function activeWorkspaceId() {
  return loadAuthSession()?.user.workspaces[0]?.workspace_id ?? null
}

export function isUnauthorizedError(error) {
  return typeof error === 'object' && error !== null && 'status' in error && error.status === 401
}
