import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useUiStore } from '@/stores/ui'
import type { AppPage } from '@/lib/navigation'

import WorkspaceView from '@/views/WorkspaceView.vue'
import ConfirmView from '@/views/ConfirmView.vue'
import RunView from '@/views/RunView.vue'
import ReviewView from '@/views/ReviewView.vue'
import ReportView from '@/views/ReportView.vue'
import ResearchView from '@/views/ResearchView.vue'
import CompetitorsView from '@/views/CompetitorsView.vue'

const routes: RouteRecordRaw[] = [
  { path: '/', redirect: '/workspace' },
  { path: '/workspace', name: 'workspace', component: WorkspaceView },
  { path: '/confirm', name: 'confirm', component: ConfirmView },
  { path: '/run', name: 'run', component: RunView },
  { path: '/review', name: 'review', component: ReviewView },
  { path: '/report', name: 'report', component: ReportView },
  { path: '/research', name: 'research', component: ResearchView },
  { path: '/competitors', name: 'competitors', component: CompetitorsView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const uiStore = useUiStore()
  const page = to.name as AppPage
  if (page && page !== uiStore.currentPage) {
    uiStore.setCurrentPage(page)
  }
})

export default router
