import assert from 'node:assert/strict'
import { test } from 'node:test'

import { buildAuditEvents, buildResearchTimeline, buildResearchWorkbenchSummary } from './researchTimeline.js'

const baseEvent = {
  id: 'event-1',
  run_id: 'run-1',
  sequence_no: 1,
  type: 'node.started',
  stage: 'plan_research',
  message: 'plan_research started',
  payload: {
    stage: 'plan_research',
    node_name: 'plan_research',
    duration_ms: 0,
    input_summary: { task_id: 'task-1' },
    output_summary: {},
  },
  created_at: '2026-08-14T10:00:00Z',
}

test('buildResearchTimeline merges lifecycle events into node status cards', () => {
  const timeline = buildResearchTimeline([
    baseEvent,
    {
      ...baseEvent,
      id: 'event-2',
      sequence_no: 2,
      type: 'node.succeeded',
      message: 'plan_research succeeded',
      payload: {
        ...baseEvent.payload,
        duration_ms: 1560,
        output_summary: { current_stage: 'planning', sources_created: 3 },
      },
      created_at: '2026-08-14T10:00:02Z',
    },
    {
      ...baseEvent,
      id: 'event-3',
      sequence_no: 3,
      type: 'source.discovered',
      message: '业务事件不应该进入节点时间线',
    },
    {
      ...baseEvent,
      id: 'event-4',
      sequence_no: 4,
      type: 'node.failed',
      stage: 'fetch_sources',
      message: 'fetch_sources failed',
      payload: {
        stage: 'fetch_sources',
        node_name: 'fetch_sources',
        duration_ms: 440,
        input_summary: {},
        output_summary: {},
        error: 'timeout',
      },
      created_at: '2026-08-14T10:00:05Z',
    },
  ])

  assert.equal(timeline.length, 2)
  assert.deepEqual(timeline[0], {
    key: 'plan_research',
    nodeName: 'plan_research',
    label: '研究规划',
    description: '理解研究需求，拆解竞品、维度和检索策略。',
    status: 'succeeded',
    statusLabel: '已完成',
    startedAt: '2026-08-14T10:00:00Z',
    updatedAt: '2026-08-14T10:00:02Z',
    durationMs: 1560,
    summary: '阶段 planning · 来源 3',
    error: '',
  })
  assert.equal(timeline[1].label, '网页抓取')
  assert.equal(timeline[1].description, '抓取网页内容并保存 HTML 快照。')
  assert.equal(timeline[1].statusLabel, '失败')
  assert.equal(timeline[1].summary, 'timeout')
})

test('buildAuditEvents surfaces input and output summaries for node events', () => {
  const events = buildAuditEvents([
    {
      ...baseEvent,
      id: 'event-2',
      sequence_no: 2,
      type: 'node.succeeded',
      message: 'plan_research succeeded',
      payload: {
        ...baseEvent.payload,
        input_summary: { task_id: 'task-1', competitor_count: 2 },
        output_summary: { current_stage: 'planning', sources_created: 3 },
      },
      created_at: '2026-08-14T10:00:02Z',
    },
  ])

  assert.equal(events[0].text, 'plan_research succeeded')
  assert.equal(events[0].detail, '输入：任务 task-1 · 竞品 2 · 输出：阶段 planning · 来源 3')
})

test('buildAuditEvents labels node and business events accurately', () => {
  const events = buildAuditEvents([
    baseEvent,
    { ...baseEvent, id: 'event-2', sequence_no: 2, type: 'run.failed', message: 'run failed', payload: {} },
    { ...baseEvent, id: 'event-3', sequence_no: 3, type: 'report.created', message: 'report created', payload: {} },
    { ...baseEvent, id: 'event-4', sequence_no: 4, type: 'unknown.thing', message: 'unknown event', payload: {} },
  ])

  assert.equal(events[0].type, '研究规划')
  assert.equal(events[1].type, '运行')
  assert.equal(events[2].type, '报告')
  assert.equal(events[3].type, 'unknown.thing')
})

test('buildResearchTimeline shows a queued placeholder before node events arrive', () => {
  const timeline = buildResearchTimeline([], {
    id: 'run-1',
    status: 'queued',
    current_stage: 'queued',
    queued_at: '2026-08-14T09:59:00Z',
  })

  assert.deepEqual(timeline, [
    {
      key: 'queued',
      nodeName: 'queued',
      label: '等待启动',
      status: 'started',
      statusLabel: '排队中',
      startedAt: '2026-08-14T09:59:00Z',
      updatedAt: '2026-08-14T09:59:00Z',
      durationMs: 0,
      summary: '研究任务已进入执行队列，正在等待 workflow 启动。',
      error: '',
    },
  ])
})

test('buildResearchWorkbenchSummary reports progress, evidence counts, and failure reasons', () => {
  const summary = buildResearchWorkbenchSummary(
    [
      baseEvent,
      {
        ...baseEvent,
        id: 'event-2',
        sequence_no: 2,
        type: 'node.succeeded',
        message: 'plan_research succeeded',
        payload: {
          ...baseEvent.payload,
          duration_ms: 600,
          output_summary: { current_stage: 'planning' },
        },
        created_at: '2026-08-14T10:00:01Z',
      },
      {
        ...baseEvent,
        id: 'event-3',
        sequence_no: 3,
        type: 'node.started',
        stage: 'discover_sources',
        message: 'discover_sources started',
        payload: {
          stage: 'discover_sources',
          node_name: 'discover_sources',
          duration_ms: 0,
          input_summary: {},
          output_summary: {},
        },
        created_at: '2026-08-14T10:00:02Z',
      },
      {
        ...baseEvent,
        id: 'event-4',
        sequence_no: 4,
        type: 'node.failed',
        stage: 'fetch_sources',
        message: 'fetch_sources failed',
        payload: {
          stage: 'fetch_sources',
          node_name: 'fetch_sources',
          duration_ms: 440,
          input_summary: {},
          output_summary: {},
          error: 'request timed out',
        },
        created_at: '2026-08-14T10:00:03Z',
      },
    ],
    { evidenceCount: 5, claimCount: 2 },
  )

  assert.equal(summary.completedNodes, 1)
  assert.equal(summary.totalNodes, 3)
  assert.equal(summary.progressPercent, 33)
  assert.equal(summary.currentStageLabel, '网页抓取')
  assert.equal(summary.failureReason, '网页抓取：request timed out')
  assert.equal(summary.evidenceCount, 5)
  assert.equal(summary.claimCount, 2)
})

test('buildResearchWorkbenchSummary includes queued placeholder progress', () => {
  const summary = buildResearchWorkbenchSummary(
    [],
    { evidenceCount: 0, claimCount: 0 },
    {
      id: 'run-1',
      status: 'queued',
      current_stage: 'queued',
      queued_at: '2026-08-14T09:59:00Z',
    },
  )

  assert.equal(summary.completedNodes, 0)
  assert.equal(summary.totalNodes, 1)
  assert.equal(summary.progressPercent, 0)
  assert.equal(summary.currentStageLabel, '等待启动')
})

test('buildResearchWorkbenchSummary exposes node status counts for the run page', () => {
  const summary = buildResearchWorkbenchSummary(
    [
      baseEvent,
      {
        ...baseEvent,
        id: 'event-2',
        sequence_no: 2,
        type: 'node.succeeded',
        message: 'plan_research succeeded',
        payload: {
          ...baseEvent.payload,
          duration_ms: 600,
          output_summary: { current_stage: 'planning' },
        },
        created_at: '2026-08-14T10:00:01Z',
      },
      {
        ...baseEvent,
        id: 'event-3',
        sequence_no: 3,
        type: 'node.started',
        stage: 'discover_sources',
        message: 'discover_sources started',
        payload: {
          stage: 'discover_sources',
          node_name: 'discover_sources',
          duration_ms: 0,
          input_summary: {},
          output_summary: {},
        },
        created_at: '2026-08-14T10:00:02Z',
      },
      {
        ...baseEvent,
        id: 'event-4',
        sequence_no: 4,
        type: 'node.failed',
        stage: 'fetch_sources',
        message: 'fetch_sources failed',
        payload: {
          stage: 'fetch_sources',
          node_name: 'fetch_sources',
          duration_ms: 440,
          input_summary: {},
          output_summary: {},
          error: 'request timed out',
        },
        created_at: '2026-08-14T10:00:03Z',
      },
    ],
    { evidenceCount: 5, claimCount: 2 },
  )

  assert.deepEqual(summary.statusCounts, {
    started: 1,
    succeeded: 1,
    failed: 1,
    skipped: 0,
    retrying: 0,
  })
  assert.equal(summary.currentStageLabel, '网页抓取')
})
