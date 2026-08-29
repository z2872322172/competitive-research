<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import {
  BellRing,
  BookOpen,
  ChevronDown,
  Database,
  FolderOpen,
  Gauge,
  Library,
  LogOut,
  Sparkles,
} from 'lucide-vue-next'
import { apiWhoami } from '@/api'
import { isUnauthorizedError, loadAuthSession, saveAuthSession } from '@/lib/authSession'
import { type AppPage } from '@/lib/navigation'
import { useAuthStore } from '@/stores/auth'
import { useTasksStore } from '@/stores/tasks'
import { useUiStore } from '@/stores/ui'

type Page = AppPage

type NavItem = {
  page: Page
  label: string
  icon: typeof Gauge
  enabled: boolean
}

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const tasksStore = useTasksStore()
const uiStore = useUiStore()

// 报告详情页使用沉浸式阅读器布局，隐藏全局侧边导航和顶栏
const isImmersivePage = computed(() => route.name === 'report')

const currentPage = computed(() => uiStore.currentPage)

const authUser = computed(() => authStore.authUser)
// 登录表单字段需要可写（v-model 与内联赋值），用 storeToRefs 解构出可写 ref；
// 之前绑定的只读 computed 没有 setter，输入无法同步回 store，导致登录前置校验误报「请输入密码」。
const {
  authFormOpen,
  authFormMode,
  authUsername,
  authPassword,
  authWorkspace,
  authError,
  authSubmitting,
  userMenuOpen,
} = storeToRefs(authStore)
const errorMessage = computed(() => authStore.errorMessage)
const userInitial = computed(() => authStore.userInitial)

// 保留 tasksStore 引用以供未来扩展
void tasksStore

function toggleAuthForm() {
  authStore.toggleAuthForm()
}

function requireLogin(message = '') {
  authStore.requireLogin(message)
}

async function submitAuthForm() {
  await authStore.submitAuthForm(() => {
    void loadTasks()
    void loadCompetitors()
  })
}

function logout() {
  authStore.logout()
  void loadTasks()
  void loadCompetitors()
}

const navItems: NavItem[] = [
  { page: 'workspace', label: '工作台', icon: Gauge, enabled: true },
  { page: 'research', label: '我的调研', icon: FolderOpen, enabled: true },
  { page: 'competitors', label: '竞品库', icon: Database, enabled: true },
  { page: 'workspace', label: '知识库', icon: Library, enabled: false },
  { page: 'workspace', label: '情报监控', icon: BellRing, enabled: false },
]

const displayMessage = computed(() => errorMessage.value)

function go(page: Page) {
  router.push({ name: page })
}

async function loadTasks() {
  await tasksStore.loadTasks(requireLogin)
}

async function loadCompetitors() {
  await tasksStore.loadCompetitors()
}

onMounted(async () => {
  const session = loadAuthSession()
  if (session?.token) {
    try {
      const user = await apiWhoami()
      saveAuthSession({ token: session.token, user })
      authStore.setUser(user)
    } catch (error) {
      if (isUnauthorizedError(error)) {
        requireLogin('登录已过期，请重新登录。')
        return
      }
    }
  }
  void loadTasks()
  void loadCompetitors()
})
</script>

<template>
  <div class="app-shell" :class="{ immersive: isImmersivePage }">
    <aside v-if="!isImmersivePage" class="sidebar">
      <button class="brand-row" type="button" @click="go('workspace')">
        <span class="brand-mark"><Sparkles :size="18" /></span>
        <span>Verda</span>
      </button>

      <nav class="nav-list" aria-label="主导航">
        <button
          v-for="item in navItems"
          :key="item.label"
          class="nav-item"
          :class="{ active: currentPage === item.page && item.enabled, disabled: !item.enabled }"
          type="button"
          :disabled="!item.enabled"
          @click="go(item.page)"
        >
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <section class="workspace-summary" aria-label="工作区摘要">
        <div>
          <BookOpen :size="17" />
          <strong>研究工作区</strong>
        </div>
        <dl>
          <dt>本月报告</dt>
          <dd>8</dd>
          <dt>证据沉淀</dt>
          <dd>221</dd>
          <dt>平均覆盖率</dt>
          <dd>92%</dd>
        </dl>
      </section>
    </aside>

    <main class="main-surface">
      <header v-if="!isImmersivePage" class="global-topbar">
        <span class="topbar-crumb">{{ navItems.find((item) => item.page === currentPage && item.enabled)?.label ?? '工作台' }}</span>
        <div class="topbar-user">
          <div v-if="authUser" class="user-menu-wrap">
            <button
              class="user-avatar-button"
              type="button"
              aria-haspopup="menu"
              :aria-expanded="userMenuOpen"
              @click="userMenuOpen = !userMenuOpen; authFormOpen = false"
            >
              <span class="user-avatar">{{ userInitial }}</span>
              <span class="user-name">{{ authUser.display_name || authUser.username }}</span>
              <ChevronDown :size="14" />
            </button>
            <div v-if="userMenuOpen" class="user-menu" role="menu">
              <div class="user-menu-head">
                <span class="user-avatar large">{{ userInitial }}</span>
                <div>
                  <strong>{{ authUser.display_name || authUser.username }}</strong>
                  <small>@{{ authUser.username }}</small>
                </div>
              </div>
              <div class="user-menu-meta">
                <span>当前工作区</span>
                <code>{{ authUser.workspaces[0]?.workspace_id ?? '-' }}</code>
              </div>
              <button class="user-menu-item danger" type="button" role="menuitem" @click="logout">
                <LogOut :size="15" />
                退出登录
              </button>
            </div>
          </div>
          <div v-else class="user-menu-wrap">
            <button class="user-login-button" type="button" :aria-expanded="authFormOpen" @click="toggleAuthForm">
              <span class="user-avatar ghost">访</span>
              登录 / 注册
            </button>
            <form v-if="authFormOpen" class="auth-panel" @submit.prevent="submitAuthForm">
              <h2>{{ authFormMode === 'login' ? '登录 Verda' : '注册新账号' }}</h2>
              <p class="auth-hint">
                {{ authFormMode === 'login' ? '输入账号密码进入你的研究工作区。' : '注册后自动创建个人工作区；填写共享工作区 ID 可加入团队。' }}
              </p>
              <label class="auth-field">
                <span>用户名</span>
                <input v-model="authUsername" type="text" autocomplete="username" required minlength="3" placeholder="username" />
              </label>
              <label class="auth-field">
                <span>密码</span>
                <input v-model="authPassword" type="password" autocomplete="current-password" required minlength="8" placeholder="至少 8 位" />
              </label>
              <label v-if="authFormMode === 'register'" class="auth-field">
                <span>共享工作区 ID（可选）</span>
                <input v-model="authWorkspace" type="text" placeholder="留空则创建个人工作区" />
              </label>
              <p v-if="authError" class="auth-error">{{ authError }}</p>
              <button class="auth-submit" type="submit" :disabled="authSubmitting">
                {{ authSubmitting ? '处理中…' : authFormMode === 'login' ? '登录' : '注册并登录' }}
              </button>
              <button
                class="auth-switch"
                type="button"
                @click="authFormMode = authFormMode === 'login' ? 'register' : 'login'; authError = ''"
              >
                {{ authFormMode === 'login' ? '没有账号？注册一个' : '已有账号？直接登录' }}
              </button>
            </form>
          </div>
        </div>
      </header>

      <p v-if="displayMessage" class="error-banner">{{ displayMessage }}</p>
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 192px minmax(0, 1fr);
  background: #f4f6f5;
}

.app-shell.immersive {
  grid-template-columns: minmax(0, 1fr);
}

.sidebar {
  position: sticky;
  top: 0;
  min-height: 100vh;
  padding: 20px 10px 14px;
  border-right: 1px solid #dce3df;
  background: #fbfcfb;
  display: flex;
  flex-direction: column;
}

.brand-row {
  width: 100%;
  height: 44px;
  padding: 0 10px;
  border: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  color: #1f2b25;
  background: transparent;
  text-align: left;
  font-size: 22px;
  font-weight: 760;
  letter-spacing: 0;
}

.brand-mark {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  color: #fff;
  background: #2f6f56;
}

.nav-list {
  display: grid;
  gap: 4px;
  margin-top: 34px;
}

.nav-item {
  height: 42px;
  padding: 0 10px;
  border: 0;
  border-radius: 7px;
  display: flex;
  align-items: center;
  gap: 11px;
  color: #66726c;
  background: transparent;
  text-align: left;
  font-size: 14px;
}

.nav-item:hover {
  color: #22342b;
  background: #eef2f0;
}

.nav-item.active {
  color: #23513f;
  background: #e2eee8;
  font-weight: 720;
}

.nav-item.disabled {
  color: #a2aaa5;
}

.workspace-summary {
  margin-top: auto;
  padding: 14px;
  border: 1px solid #dfe6e2;
  border-radius: 8px;
  background: #f6f8f7;
}

.workspace-summary > div {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #384b42;
  font-size: 13px;
}

.workspace-summary dl {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px 12px;
  margin: 14px 0 0;
  color: #738079;
  font-size: 12px;
}

.workspace-summary dt,
.workspace-summary dd {
  margin: 0;
}

.workspace-summary dd {
  color: #24342d;
  font-weight: 760;
}

.main-surface {
  min-width: 0;
  min-height: 100vh;
}

.error-banner {
  margin: 16px clamp(22px, 3.8vw, 48px) 0;
  padding: 11px 14px;
  border: 1px solid #ead3a5;
  border-radius: 7px;
  color: #7b5522;
  background: #fff7e8;
  font-size: 13px;
  line-height: 1.5;
}

.global-topbar {
  position: sticky;
  top: 0;
  z-index: 40;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  height: 56px;
  padding: 0 clamp(20px, 4vw, 54px);
  border-bottom: 1px solid #e2e8e4;
  background: rgba(251, 252, 251, 0.88);
  backdrop-filter: blur(10px);
}

.topbar-crumb {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: #66726c;
}

.topbar-user {
  position: relative;
  display: flex;
  align-items: center;
}

.user-menu-wrap {
  position: relative;
}

.user-avatar-button,
.user-login-button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid transparent;
  border-radius: 999px;
  padding: 4px 10px 4px 4px;
  background: transparent;
  color: #3c4a43;
  font-size: 13px;
  font-weight: 600;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.user-avatar-button:hover,
.user-login-button:hover {
  background: #eef3f0;
  border-color: #dfe7e2;
}

.user-avatar {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2f6f56, #4f9a78);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
  box-shadow: inset 0 -6px 12px rgba(0, 0, 0, 0.14);
}

.user-avatar.large {
  width: 40px;
  height: 40px;
  font-size: 17px;
}

.user-avatar.ghost {
  background: #eef3f0;
  color: #66726c;
  border: 1px dashed #b9c8c0;
  box-shadow: none;
}

.user-name {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 60;
  width: 264px;
  padding: 14px;
  border: 1px solid #dfe7e2;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 18px 44px rgba(32, 42, 37, 0.14);
  display: flex;
  flex-direction: column;
  gap: 12px;
  animation: overlay-pop 0.16s ease;
}

.user-menu-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-menu-head strong {
  display: block;
  font-size: 14px;
  color: #202a25;
}

.user-menu-head small {
  color: #77847d;
  font-size: 12px;
}

.user-menu-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  border-radius: 9px;
  background: #f4f7f5;
  font-size: 12px;
  color: #66726c;
}

.user-menu-meta code {
  font-family: inherit;
  color: #2f5d49;
  word-break: break-all;
}

.user-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 0;
  border-radius: 9px;
  padding: 8px 10px;
  background: transparent;
  font-size: 13px;
  color: #3c4a43;
  text-align: left;
}

.user-menu-item:hover {
  background: #f1f5f2;
}

.user-menu-item.danger {
  color: #b3362b;
}

.user-menu-item.danger:hover {
  background: #fdf0ee;
}

.auth-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 60;
  width: 320px;
  background: #ffffff;
  border: 1px solid #dfe7e2;
  border-radius: 16px;
  padding: 22px;
  box-shadow: 0 18px 44px rgba(32, 42, 37, 0.14);
  display: flex;
  flex-direction: column;
  gap: 12px;
  animation: overlay-pop 0.16s ease;
}

.auth-panel h2 {
  margin: 0;
  font-size: 20px;
}

.auth-hint {
  margin: 0;
  color: #5d6b64;
  font-size: 13px;
  line-height: 1.5;
}

.auth-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: #3c4a43;
}

.auth-field input {
  border: 1px solid #cfdad3;
  border-radius: 8px;
  padding: 9px 12px;
  font-size: 14px;
  background: #fbfdfc;
}

.auth-field input:focus {
  outline: 2px solid #2f7d5d;
  outline-offset: 1px;
}

.auth-error {
  margin: 0;
  color: #b3362b;
  font-size: 13px;
}

.auth-submit {
  border: none;
  border-radius: 10px;
  padding: 11px 16px;
  background: #2f7d5d;
  color: #fff;
  font-size: 15px;
  cursor: pointer;
}

.auth-submit:disabled {
  opacity: 0.6;
  cursor: default;
}

.auth-switch {
  border: none;
  background: none;
  color: #2f7d5d;
  font-size: 13px;
  cursor: pointer;
  padding: 4px;
}

@keyframes overlay-pop {
  from {
    opacity: 0;
    transform: translateY(-6px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@media (max-width: 820px) {
  .app-shell {
    grid-template-columns: 1fr;
  }

  .sidebar {
    position: static;
    min-height: auto;
    border-right: 0;
    border-bottom: 1px solid #dce3df;
  }

  .nav-list {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    margin-top: 18px;
  }

  .workspace-summary {
    display: none;
  }
}
</style>
