import { describe, expect, it } from 'vitest'

import { buildResearchSyncFeedback, shouldPollResearchTask } from './polling'
import type { TaskDetailOut } from '@/api/types'

// 测试辅助：按任务状态 + 最新 run 状态构造任务详情。
function detail(taskStatus: string, runStatus: string | null = taskStatus, errorMessage: string | null = null): TaskDetailOut {
  return {
    task: {
      status: taskStatus,
      failure_reason: taskStatus === 'failed' ? 'task failure reason' : null,
    },
    latest_run: runStatus
      ? {
          status: runStatus,
          error_message: errorMessage,
        }
      : null,
  } as TaskDetailOut
}

describe('shouldPollResearchTask', () => {
  it('continues polling while the latest run is queued or running', () => {
    expect(shouldPollResearchTask(detail('queued', 'queued'))).toBe(true)
    expect(shouldPollResearchTask(detail('running', 'running'))).toBe(true)
  })

  it('stops polling for terminal latest run states', () => {
    for (const status of ['waiting_review', 'completed', 'failed', 'canceled']) {
      expect(shouldPollResearchTask(detail('running', status)), status).toBe(false)
    }
  })

  it('uses task status only when no latest run is available', () => {
    expect(shouldPollResearchTask(detail('running', null))).toBe(true)
    expect(shouldPollResearchTask(detail('completed', null))).toBe(false)
  })
})

describe('buildResearchSyncFeedback', () => {
  it('reports a waiting message when an active task has no events yet', () => {
    const feedback = buildResearchSyncFeedback({ detail: detail('running', 'running'), events: [] })!

    expect(feedback.tone).toBe('info')
    expect(feedback.title).toMatch(/等待/)
    expect(feedback.message).toMatch(/第一条节点事件/)
  })

  it('reports terminal failure details without changing polling state', () => {
    const failedDetail = detail('failed', 'failed', 'fetch timeout')
    const feedback = buildResearchSyncFeedback({ detail: failedDetail, events: [] })!

    expect(shouldPollResearchTask(failedDetail)).toBe(false)
    expect(feedback.tone).toBe('error')
    expect(feedback.message).toMatch(/fetch timeout/)
  })

  it('keeps polling after a temporary API error and asks for a later retry', () => {
    const activeDetail = detail('running', 'running')
    const feedback = buildResearchSyncFeedback({ detail: activeDetail, events: [], error: new Error('503') })!

    expect(shouldPollResearchTask(activeDetail)).toBe(true)
    expect(feedback.tone).toBe('warning')
    expect(feedback.message).toMatch(/稍后自动重试/)
    expect(feedback.message).toMatch(/503/)
  })

  it('describes completed tasks even when the event list is empty', () => {
    const feedback = buildResearchSyncFeedback({ detail: detail('completed', 'completed'), events: [] })!

    expect(feedback.tone).toBe('success')
    expect(feedback.message).toMatch(/已完成/)
  })
})
