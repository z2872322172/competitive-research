import { describe, expect, it } from 'vitest'

import { nextPageAfterReview, nextPageAfterTaskRefresh } from './navigation'
import type { TaskDetailOut } from '@/api/types'

describe('nextPageAfterReview', () => {
  it('opens report after review completes with a report', () => {
    const detail = {
      task: { status: 'completed' },
      reports: [{ id: 1, version: 1 }],
    } as unknown as TaskDetailOut

    expect(nextPageAfterReview(detail, 'accept')).toBe('report')
  })

  it('stays on review while task is not complete', () => {
    const detail = {
      task: { status: 'waiting_review' },
      reports: [{ id: 1, version: 1 }],
    } as unknown as TaskDetailOut

    expect(nextPageAfterReview(detail, 'exclude')).toBe('review')
  })

  it('returns run when reviewer requests more research', () => {
    const detail = {
      task: { status: 'waiting_review' },
      reports: [{ id: 1, version: 1 }],
    } as unknown as TaskDetailOut

    expect(nextPageAfterReview(detail, 'continue_research')).toBe('run')
  })
})

describe('nextPageAfterTaskRefresh', () => {
  it('opens report after a waiting-review task completes with a report', () => {
    const detail = {
      task: { status: 'completed' },
      reports: [{ id: 1, version: 2 }],
    } as unknown as TaskDetailOut

    expect(nextPageAfterTaskRefresh(detail, 'run')).toBe('report')
  })
})
