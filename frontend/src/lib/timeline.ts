import type { ResearchEventOut, TaskRunOut } from '@/api/types'

export type ResearchTimelineStatus = 'started' | 'succeeded' | 'failed' | 'skipped' | 'retrying'

export type ResearchTimelineItem = {
  key: string
  nodeName: string
  label: string
  description?: string
  status: ResearchTimelineStatus
  statusLabel: string
  startedAt: string
  updatedAt: string
  durationMs: number
  summary: string
  error: string
}

export type ResearchAuditEvent = {
  type: string
  rawType: string
  time: string
  text: string
  detail: string
}

export type ResearchWorkbenchSummary = {
  completedNodes: number
  totalNodes: number
  progressPercent: number
  currentStageLabel: string
  evidenceCount: number
  claimCount: number
  statusCounts: {
    started: number
    succeeded: number
    failed: number
    skipped: number
    retrying: number
  }
  failureReason: string
}

const NODE_LABELS: Record<string, string> = {
  initialize_run: '初始化任务',
  plan_research: '研究规划',
  build_search_plan: '检索计划',
  discover_sources: '来源发现',
  fetch_sources: '网页抓取',
  parse_sources: '正文解析',
  extract_evidence: '证据抽取',
  extract_claims: 'Claim 抽取',
  verify_claims: '引用质检',
  generate_report: '报告生成',
  review_gate: '等待审阅',
}

const STATUS_LABELS: Record<ResearchTimelineStatus, string> = {
  started: '进行中',
  succeeded: '已完成',
  failed: '失败',
  skipped: '已跳过',
  retrying: '重试中',
}

const NODE_DESCRIPTIONS: Record<string, string> = {
  initialize_run: '准备任务运行环境，加载研究范围和初始状态。',
  plan_research: '理解研究需求，拆解竞品、维度和检索策略。',
  build_search_plan: '为每个竞品和维度生成具体的检索关键词计划。',
  discover_sources: '通过搜索或手动 URL 发现候选来源。',
  fetch_sources: '抓取网页内容并保存 HTML 快照。',
  parse_sources: '从原始 HTML 中解析出干净的正文和元数据。',
  extract_evidence: '从正文中抽取可引用的证据片段并记录定位。',
  extract_claims: '从证据中提取结构化竞品结论。',
  verify_claims: '检查结论的引用完整性、置信度和冲突风险。',
  generate_report: '基于已验证结论生成带引用的结构化报告。',
  review_gate: '等待人工审阅风险结论后继续生成最终报告。',
}

const RUN_PLACEHOLDERS: Partial<Record<string, Omit<ResearchTimelineItem, 'startedAt' | 'updatedAt' | 'durationMs' | 'error'>>> = {
  queued: {
    key: 'queued',
    nodeName: 'queued',
    label: '等待启动',
    status: 'started',
    statusLabel: '排队中',
    summary: '研究任务已进入执行队列，正在等待 workflow 启动。',
  },
  running: {
    key: 'initialize_run',
    nodeName: 'initialize_run',
    label: '初始化任务',
    status: 'started',
    statusLabel: '启动中',
    summary: 'workflow 正在启动，节点事件即将写入时间线。',
  },
}

const SUMMARY_LABELS: Record<string, string> = {
  run_status: '运行',
  current_stage: '阶段',
  sources_created: '来源',
  evidence_created: '证据',
  claims_created: 'Claim',
  claims_without_evidence: '缺证据',
  verified_claims: '已验证',
  corroborated_claims: '多源印证',
  low_confidence_claims: '低置信',
  conflict_claims: '冲突',
  citation_coverage: '引用覆盖',
}

const AUDIT_SUMMARY_LABELS: Record<string, string> = {
  task_id: '任务',
  competitor_count: '竞品',
  current_stage: '阶段',
  sources_created: '来源',
  evidence_created: '证据',
  claims_created: 'Claim',
  verified_claims: '已验证',
  corroborated_claims: '多源印证',
  low_confidence_claims: '低置信度',
  conflict_claims: '冲突',
  citation_coverage: '引用覆盖',
}

const EVENT_TYPE_LABELS: Record<string, string> = {
  'planning.started': '规划',
  'search.started': '检索',
  'source.found': '来源',
  'evidence.created': '证据',
  'claim.created': '结论',
  'claim.verified': '验证',
  'claim.conflict_detected': '冲突',
  'review.required': '审核',
  'review.decision_created': '审核',
  'report.created': '报告',
  'report.section_updated': '报告',
  'report.generate_failed': '报告',
  'run.failed': '运行',
  'run.canceled': '运行',
  'run.resume_requested': '运行',
  'task.completed': '任务',
}

const KNOWN_NODE_ORDER = Object.keys(NODE_LABELS)

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function getNodeName(event: ResearchEventOut): string {
  const payload = asRecord(event.payload)
  return String(payload.node_name || payload.stage || event.stage || 'unknown_node')
}

function getLifecycleStatus(type: string): string {
  return type.startsWith('node.') ? type.slice('node.'.length) : ''
}

function formatSummaryValue(key: string, value: unknown): string {
  if (key === 'citation_coverage' && typeof value === 'number') {
    return `${Math.round(value * 100)}%`
  }
  return String(value)
}

function formatOutputSummary(outputSummary: Record<string, unknown>): string {
  return Object.entries(outputSummary)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => `${SUMMARY_LABELS[key] || key} ${formatSummaryValue(key, value)}`)
    .join(' · ')
}

function sortTimeline(left: ResearchTimelineItem, right: ResearchTimelineItem): number {
  const leftIndex = KNOWN_NODE_ORDER.indexOf(left.nodeName)
  const rightIndex = KNOWN_NODE_ORDER.indexOf(right.nodeName)
  if (leftIndex !== -1 && rightIndex !== -1) return leftIndex - rightIndex
  if (leftIndex !== -1) return -1
  if (rightIndex !== -1) return 1
  return left.updatedAt.localeCompare(right.updatedAt)
}

function buildRunPlaceholder(latestRun: TaskRunOut | null | undefined): ResearchTimelineItem | null {
  const placeholder = latestRun?.status ? RUN_PLACEHOLDERS[latestRun.status] : undefined
  if (!placeholder || !latestRun) return null
  const timestamp = latestRun.started_at || latestRun.queued_at || ''
  return {
    ...placeholder,
    startedAt: timestamp,
    updatedAt: timestamp,
    durationMs: 0,
    error: '',
  }
}

export function buildResearchTimeline(events: ResearchEventOut[], latestRun: TaskRunOut | null = null): ResearchTimelineItem[] {
  const byNode = new Map<string, ResearchTimelineItem>()

  for (const event of events || []) {
    const status = getLifecycleStatus(event.type)
    if (!status || !(status in STATUS_LABELS)) continue

    const payload = asRecord(event.payload)
    const nodeName = getNodeName(event)
    const outputSummary = asRecord(payload.output_summary)
    const previous = byNode.get(nodeName)
    const durationMs = Number(payload.duration_ms ?? previous?.durationMs ?? 0)
    const error = typeof payload.error === 'string' ? payload.error : ''
    const summary = error || formatOutputSummary(outputSummary) || event.message

    byNode.set(nodeName, {
      key: nodeName,
      nodeName,
      label: NODE_LABELS[nodeName] || nodeName,
      description: NODE_DESCRIPTIONS[nodeName] || '',
      status: status as ResearchTimelineStatus,
      statusLabel: STATUS_LABELS[status as ResearchTimelineStatus],
      startedAt: previous?.startedAt || (status === 'started' ? event.created_at : ''),
      updatedAt: event.created_at,
      durationMs,
      summary,
      error,
    })
  }

  const timeline = Array.from(byNode.values()).sort(sortTimeline)
  if (timeline.length) return timeline
  const placeholder = buildRunPlaceholder(latestRun)
  return placeholder ? [placeholder] : []
}

export function buildResearchWorkbenchSummary(
  events: ResearchEventOut[],
  counts: { evidenceCount?: number; claimCount?: number } = {},
  latestRun: TaskRunOut | null = null,
): ResearchWorkbenchSummary {
  const timeline = buildResearchTimeline(events, latestRun)
  const statusCounts: ResearchWorkbenchSummary['statusCounts'] = {
    started: 0,
    succeeded: 0,
    failed: 0,
    skipped: 0,
    retrying: 0,
  }

  for (const item of timeline) {
    if (item.status in statusCounts) {
      statusCounts[item.status] += 1
    }
  }

  const completedNodes = timeline.filter((item) => ['succeeded', 'skipped'].includes(item.status)).length
  const activeNode = timeline.find((item) => ['started', 'retrying'].includes(item.status))
  const failedNode = timeline.find((item) => item.status === 'failed')
  const currentNode = failedNode || activeNode || timeline.at(-1)
  const progressPercent = timeline.length ? Math.round((completedNodes / timeline.length) * 100) : 0

  return {
    completedNodes,
    totalNodes: timeline.length,
    progressPercent,
    currentStageLabel: currentNode?.label || '尚未开始',
    evidenceCount: Number(counts.evidenceCount || 0),
    claimCount: Number(counts.claimCount || 0),
    statusCounts,
    failureReason: failedNode ? `${failedNode.label}：${failedNode.error || failedNode.summary}` : '',
  }
}

export function formatDuration(durationMs: number): string {
  if (!durationMs) return ''
  if (durationMs < 1000) return `${durationMs} ms`
  return `${(durationMs / 1000).toFixed(1)} s`
}

function formatAuditSummary(summary: unknown): string {
  return Object.entries(asRecord(summary))
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => `${AUDIT_SUMMARY_LABELS[key] || key} ${formatSummaryValue(key, value)}`)
    .join(' · ')
}

function eventTypeLabel(event: ResearchEventOut): string {
  if (event.type.startsWith('node.')) {
    const nodeName = getNodeName(event)
    return NODE_LABELS[nodeName] || nodeName
  }
  return EVENT_TYPE_LABELS[event.type] || event.type
}

export function buildAuditEvents(events: ResearchEventOut[]): ResearchAuditEvent[] {
  return events.map((event) => {
    const payload = asRecord(event.payload)
    const inputSummary = formatAuditSummary(payload.input_summary)
    const outputSummary = formatAuditSummary(payload.output_summary)
    const detailParts: string[] = []
    if (inputSummary) detailParts.push(`输入：${inputSummary}`)
    if (outputSummary) detailParts.push(`输出：${outputSummary}`)
    return {
      type: eventTypeLabel(event),
      rawType: event.type,
      time: event.created_at,
      text: event.message,
      detail: detailParts.join(' · '),
    }
  })
}
