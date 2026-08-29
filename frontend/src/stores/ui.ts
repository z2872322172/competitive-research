import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AppPage } from '@/lib/navigation'

export const useUiStore = defineStore('ui', () => {
  const currentPage = ref<AppPage>('workspace')
  const isExporting = ref(false)
  const isRegeneratingReport = ref(false)

  function setCurrentPage(page: AppPage) {
    currentPage.value = page
  }

  return {
    currentPage,
    isExporting,
    isRegeneratingReport,
    setCurrentPage,
  }
})
