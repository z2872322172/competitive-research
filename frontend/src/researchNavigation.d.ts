import type { TaskDetailOut } from './api'

export type ReviewDecision = 'accept' | 'mark_uncertain' | 'exclude' | 'continue_research'

export function nextPageAfterReview(taskDetail: TaskDetailOut | null | undefined, decision?: ReviewDecision | string): 'run' | 'review' | 'report'

export function nextPageAfterTaskRefresh(taskDetail: TaskDetailOut | null | undefined, currentPage?: 'workspace' | 'confirm' | 'run' | 'review' | 'report' | 'research' | 'competitors'): 'workspace' | 'confirm' | 'run' | 'review' | 'report' | 'research' | 'competitors'
