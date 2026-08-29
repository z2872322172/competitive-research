import type { TaskDetailOut } from '@/api/types'

export type ReviewDecision = 'accept' | 'mark_uncertain' | 'exclude' | 'continue_research'

export type AppPage = 'workspace' | 'confirm' | 'run' | 'review' | 'report' | 'research' | 'competitors'

export function nextPageAfterReview(taskDetail: TaskDetailOut | null | undefined, decision: ReviewDecision | string = ''): 'run' | 'review' | 'report' {
  if (decision === 'continue_research') return 'run'
  const hasReport = Array.isArray(taskDetail?.reports) && taskDetail.reports.length > 0
  if (taskDetail?.task?.status === 'completed' && hasReport) return 'report'
  return 'review'
}

export function nextPageAfterTaskRefresh(taskDetail: TaskDetailOut | null | undefined, currentPage: AppPage = 'run'): AppPage {
  const hasReport = Array.isArray(taskDetail?.reports) && taskDetail.reports.length > 0
  if (taskDetail?.task?.status === 'completed' && hasReport) return 'report'
  return currentPage
}
