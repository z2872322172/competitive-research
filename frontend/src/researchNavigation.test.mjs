import assert from 'node:assert/strict'
import { test } from 'node:test'

import { nextPageAfterReview, nextPageAfterTaskRefresh } from './researchNavigation.js'

test('nextPageAfterReview opens report after review completes with a report', () => {
  const detail = {
    task: { status: 'completed' },
    reports: [{ id: 'report-1', version: 1 }],
  }

  assert.equal(nextPageAfterReview(detail, 'accept'), 'report')
})

test('nextPageAfterReview stays on review while task is not complete', () => {
  const detail = {
    task: { status: 'waiting_review' },
    reports: [{ id: 'report-1', version: 1 }],
  }

  assert.equal(nextPageAfterReview(detail, 'exclude'), 'review')
})

test('nextPageAfterReview returns run when reviewer requests more research', () => {
  const detail = {
    task: { status: 'waiting_review' },
    reports: [{ id: 'report-1', version: 1 }],
  }

  assert.equal(nextPageAfterReview(detail, 'continue_research'), 'run')
})

test('nextPageAfterTaskRefresh opens report after a waiting-review task completes with a report', () => {
  const detail = {
    task: { status: 'completed' },
    reports: [{ id: 'report-1', version: 2 }],
  }

  assert.equal(nextPageAfterTaskRefresh(detail, 'run'), 'report')
})
