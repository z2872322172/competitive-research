import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiLogin, apiRegister, buildAuthSession } from '@/api'
import { clearAuthSession, loadAuthSession, saveAuthSession, type AuthUser } from '@/lib/authSession'

export const useAuthStore = defineStore('auth', () => {
  const authUser = ref<AuthUser | null>(loadAuthSession()?.user ?? null)
  const authFormOpen = ref(false)
  const authFormMode = ref<'login' | 'register'>('login')
  const authUsername = ref('probe_test')
  const authPassword = ref('probe123456')
  const authWorkspace = ref('')
  const authError = ref('')
  const authSubmitting = ref(false)
  const userMenuOpen = ref(false)
  const errorMessage = ref('')

  let authPromptShown = false

  const userInitial = computed(() => {
    const source = authUser.value?.display_name || authUser.value?.username || '访'
    return source.trim().charAt(0).toUpperCase()
  })

  function closeUserOverlays() {
    authFormOpen.value = false
    userMenuOpen.value = false
  }

  function toggleAuthForm() {
    userMenuOpen.value = false
    authError.value = ''
    authFormOpen.value = !authFormOpen.value
  }

  function requireLogin(message = '') {
    clearAuthSession()
    authUser.value = null
    authError.value = message
    authFormMode.value = 'login'
    if (!authPromptShown) {
      authFormOpen.value = true
      authPromptShown = true
    }
    userMenuOpen.value = false
  }

  async function submitAuthForm(onSuccess?: () => void) {
    if (authSubmitting.value) return
    // 前置校验：浏览器自动填充或回车提交可能绕过表单原生校验，空密码不再发到后端。
    if (!authUsername.value.trim()) {
      authError.value = '请输入用户名。'
      return
    }
    if (authFormMode.value === 'register' ? authPassword.value.length < 8 : !authPassword.value) {
      authError.value = authFormMode.value === 'register' ? '密码至少需要 8 位。' : '请输入密码。'
      return
    }
    authSubmitting.value = true
    authError.value = ''
    try {
      const response =
        authFormMode.value === 'register'
          ? await apiRegister(authUsername.value.trim(), authPassword.value, authWorkspace.value.trim() || undefined)
          : await apiLogin(authUsername.value.trim(), authPassword.value)
      const session = buildAuthSession(response)
      saveAuthSession(session)
      authUser.value = session.user
      authFormOpen.value = false
      authPassword.value = ''
      authWorkspace.value = ''
      authPromptShown = false
      errorMessage.value = ''
      onSuccess?.()
    } catch (error) {
      authError.value = error instanceof Error ? error.message : '登录失败，请稍后重试。'
    } finally {
      authSubmitting.value = false
    }
  }

  function logout() {
    closeUserOverlays()
    clearAuthSession()
    authUser.value = null
    errorMessage.value = '已退出登录，当前展示本地原型数据。'
  }

  function setUser(user: AuthUser) {
    authUser.value = user
  }

  function resetAuthPrompt() {
    authPromptShown = false
  }

  return {
    authUser,
    authFormOpen,
    authFormMode,
    authUsername,
    authPassword,
    authWorkspace,
    authError,
    authSubmitting,
    userMenuOpen,
    errorMessage,
    userInitial,
    closeUserOverlays,
    toggleAuthForm,
    requireLogin,
    submitAuthForm,
    logout,
    setUser,
    resetAuthPrompt,
  }
})
