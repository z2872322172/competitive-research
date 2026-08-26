import assert from 'node:assert/strict'
import { test } from 'node:test'

import { buildResearchSyncFeedback, shouldPollResearchTask } from './researchPolling.js'

function detail(taskStatus, runStatus = taskStatus, errorMessage = null) {
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
  }
}

test('continues polling while the latest run is queued or running', () => {
  assert.equal(shouldPollResearchTask(detail('queued', 'queued')), true)
  assert.equal(shouldPollResearchTask(detail('running', 'running')), true)
})

test('stops polling for terminal latest run states', () => {
  for (const status of ['waiting_review', 'completed', 'failed', 'canceled']) {
    assert.equal(shouldPollResearchTask(detail('running', status)), false, status)
  }
})

test('uses task status only when no latest run is available', () => {
  assert.equal(shouldPollResearchTask(detail('running', null)), true)
  assert.equal(shouldPollResearchTask(detail('completed', null)), false)
})

test('reports a waiting message when an active task has no events yet', () => {
  const feedback = buildResearchSyncFeedback({ detail: detail('running', 'running'), events: [] })

  assert.equal(feedback.tone, 'info')
  assert.match(feedback.title, /等待/)
  assert.match(feedback.message, /第一条节点事件/)
})

test('reports terminal failure details without changing polling state', () => {
  const failedDetail = detail('failed', 'failed', 'fetch timeout')
  const feedback = buildResearchSyncFeedback({ detail: failedDetail, events: [] })

  assert.equal(shouldPollResearchTask(failedDetail), false)
  assert.equal(feedback.tone, 'error')
  assert.match(feedback.message, /fetch timeout/)
})

test('keeps polling after a temporary API error and asks for a later retry', () => {
  const activeDetail = detail('running', 'running')
  const feedback = buildResearchSyncFeedback({ detail: activeDetail, events: [], error: new Error('503') })

  assert.equal(shouldPollResearchTask(activeDetail), true)
  assert.equal(feedback.tone, 'warning')
  assert.match(feedback.message, /稍后自动重试/)
  assert.match(feedback.message, /503/)
})

test('describes completed tasks even when the event list is empty', () => {
  const feedback = buildResearchSyncFeedback({ detail: detail('completed', 'completed'), events: [] })

  assert.equal(feedback.tone, 'success')
  assert.match(feedback.message, /已完成/)
})
