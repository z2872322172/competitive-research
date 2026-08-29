import { describe, expect, it } from 'vitest'

import { buildAuditEvents, buildResearchTimeline, buildResearchWorkbenchSummary } from './timeline'
import type { ResearchEventOut, TaskRunOut } from '@/api/types'

const baseEvent: ResearchEventOut = {
  id: 1,
  run_id: 1,
  sequence_no: 1,
  type: 'node.started',
  stage: 'plan_research',
  message: 'plan_research started',
  payload: {
    stage: 'plan_research',
    node_name: 'plan_research',
    duration_ms: 0,
    input_summary: { task_id: 1 },
    output_summary: {},
  },
  created_at: '2026-08-14T10:00:00Z',
}

describe('buildResearchTimeline', () => {
  it('merges lifecycle events into node status cards', () => {
    const timeline = buildResearchTimeline([
      baseEvent,
      {
        ...baseEvent,
        id: 2,
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
        id: 3,
        sequence_no: 3,
        type: 'source.discovered',
        message: '业务事件不应该进入节点时间线',
      },
      {
        ...baseEvent,
        id: 4,
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

    expect(timeline.length).toBe(2)
    expect(timeline[0]).toEqual({
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
    expect(timeline[1].label).toBe('网页抓取')
    expect(timeline[1].description).toBe('抓取网页内容并保存 HTML 快照。')
    expect(timeline[1].statusLabel).toBe('失败')
    expect(timeline[1].summary).toBe('timeout')
  })

  it('shows a queued placeholder before node events arrive', () => {
    const timeline = buildResearchTimeline([], {
      id: 1,
      status: 'queued',
      current_stage: 'queued',
      queued_at: '2026-08-14T09:59:00Z',
    } as TaskRunOut)

    expect(timeline).toEqual([
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
})

describe('buildAuditEvents', () => {
  it('surfaces input and output summaries for node events', () => {
    const events = buildAuditEvents([
      {
        ...baseEvent,
        id: 2,
        sequence_no: 2,
        type: 'node.succeeded',
        message: 'plan_research succeeded',
        payload: {
          ...baseEvent.payload,
          input_summary: { task_id: 1, competitor_count: 2 },
          output_summary: { current_stage: 'planning', sources_created: 3 },
        },
        created_at: '2026-08-14T10:00:02Z',
      },
    ])

    expect(events[0].text).toBe('plan_research succeeded')
    expect(events[0].detail).toBe('输入：任务 1 · 竞品 2 · 输出：阶段 planning · 来源 3')
  })

  it('labels node and business events accurately', () => {
    const events = buildAuditEvents([
      baseEvent,
      { ...baseEvent, id: 2, sequence_no: 2, type: 'run.failed', message: 'run failed', payload: {} },
      { ...baseEvent, id: 3, sequence_no: 3, type: 'report.created', message: 'report created', payload: {} },
      { ...baseEvent, id: 4, sequence_no: 4, type: 'unknown.thing', message: 'unknown event', payload: {} },
    ])

    expect(events[0].type).toBe('研究规划')
    expect(events[1].type).toBe('运行')
    expect(events[2].type).toBe('报告')
    expect(events[3].type).toBe('unknown.thing')
  })

  it('labels claim verification and conflict events accurately', () => {
    const events = buildAuditEvents([
      {
        ...baseEvent,
        id: 5,
        sequence_no: 5,
        type: 'claim.verified',
        stage: 'verify_claims',
        message: 'Claim 3（Cursor）完成多源交叉验证：corroborated，置信度 91%。',
        payload: { claim_id: 3, status: 'corroborated', confidence_score: 0.91, support_source_count: 2 },
      },
      {
        ...baseEvent,
        id: 6,
        sequence_no: 6,
        type: 'claim.conflict_detected',
        stage: 'verify_claims',
        message: 'Claim 4（Windsurf）检测到证据冲突。',
        payload: { claim_id: 4, resolution_strategy: 'mark_as_unresolved' },
      },
    ])

    expect(events[0].type).toBe('验证')
    expect(events[0].rawType).toBe('claim.verified')
    expect(events[1].type).toBe('冲突')
    expect(events[1].rawType).toBe('claim.conflict_detected')
  })

  it('labels report section updates as report events with section payload', () => {
    const events = buildAuditEvents([
      {
        ...baseEvent,
        type: 'report.section_updated',
        stage: 'verify_claims',
        message: '报告草稿已更新章节「阶段性发现」。',
        payload: { report_id: 1, version: 1, section_type: 'interim_findings', title: '阶段性发现', order_no: 6 },
      },
    ])

    expect(events[0].type).toBe('报告')
    expect(events[0].rawType).toBe('report.section_updated')
    expect(events[0].text).toBe('报告草稿已更新章节「阶段性发现」。')
  })
})

describe('buildResearchWorkbenchSummary', () => {
  const nodeEvents: ResearchEventOut[] = [
    baseEvent,
    {
      ...baseEvent,
      id: 2,
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
      id: 3,
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
      id: 4,
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
  ]

  it('reports progress, evidence counts, and failure reasons', () => {
    const summary = buildResearchWorkbenchSummary(nodeEvents, { evidenceCount: 5, claimCount: 2 })

    expect(summary.completedNodes).toBe(1)
    expect(summary.totalNodes).toBe(3)
    expect(summary.progressPercent).toBe(33)
    expect(summary.currentStageLabel).toBe('网页抓取')
    expect(summary.failureReason).toBe('网页抓取：request timed out')
    expect(summary.evidenceCount).toBe(5)
    expect(summary.claimCount).toBe(2)
  })

  it('includes queued placeholder progress', () => {
    const summary = buildResearchWorkbenchSummary(
      [],
      { evidenceCount: 0, claimCount: 0 },
      {
        id: 1,
        status: 'queued',
        current_stage: 'queued',
        queued_at: '2026-08-14T09:59:00Z',
      } as TaskRunOut,
    )

    expect(summary.completedNodes).toBe(0)
    expect(summary.totalNodes).toBe(1)
    expect(summary.progressPercent).toBe(0)
    expect(summary.currentStageLabel).toBe('等待启动')
  })

  it('exposes node status counts for the run page', () => {
    const summary = buildResearchWorkbenchSummary(nodeEvents, { evidenceCount: 5, claimCount: 2 })

    expect(summary.statusCounts).toEqual({
      started: 1,
      succeeded: 1,
      failed: 1,
      skipped: 0,
      retrying: 0,
    })
    expect(summary.currentStageLabel).toBe('网页抓取')
  })
})
