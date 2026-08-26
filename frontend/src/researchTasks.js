const STATUS_META = {
  draft: { label: '草稿', tone: 'draft', description: '任务尚未确认，可以继续编辑研究范围。' },
  confirmed: { label: '已确认', tone: 'active', description: '任务已确认，等待进入执行队列。' },
  queued: { label: '排队中', tone: 'active', description: '任务已进入队列，等待研究执行。' },
  running: { label: '运行中', tone: 'active', description: '研究流程正在执行。' },
  waiting_review: { label: '待审核', tone: 'review', description: '研究已产出 Claim 和报告草稿，等待人工审核。' },
  completed: { label: '已完成', tone: 'done', description: '审核已完成，报告可以交付。' },
  failed: { label: '失败', tone: 'failed', description: '研究执行失败，可以查看原因后重试。' },
  canceled: { label: '已取消', tone: 'canceled', description: '任务已取消，可按需重新发起研究。' },
}

const RUN_STATUS_LABELS = {
  queued: '排队中',
  running: '运行中',
  waiting_review: '待审核',
  completed: '已完成',
  failed: '失败',
  canceled: '已取消',
}

const RESEARCH_TYPE_LABELS = {
  competitive_research: '竞品研究',
  deep_research: '深度研究',
}

function latestReportCoverage(detail) {
  const reports = Array.isArray(detail?.reports) ? detail.reports : []
  const latest = reports.at(-1)
  return Math.round(Number(latest?.citation_coverage ?? 0) * 100)
}

function countItems(value) {
  return Array.isArray(value) ? value.length : 0
}

function statusReason(task, run) {
  return run?.error_message || task?.failure_reason || ''
}

export function getTaskStatusMeta(task, latestRun = null) {
  const status = task?.status || latestRun?.status || 'draft'
  const base = STATUS_META[status] || STATUS_META.draft
  const reason = statusReason(task, latestRun)
  const canRetry = status === 'failed' || latestRun?.status === 'failed' || status === 'canceled'
  const canResume = status === 'failed' && latestRun?.status === 'failed'
  const canCancel = ['confirmed', 'queued', 'running', 'waiting_review'].includes(status) || ['queued', 'running'].includes(latestRun?.status || '')

  return {
    ...base,
    rawStatus: status,
    reason,
    canRetry,
    canResume,
    canCancel,
  }
}

export function buildTaskListQuery(searchText = '', status = 'all') {
  const query = { limit: 20 }
  const q = searchText.trim()
  if (q) query.q = q
  if (status && status !== 'all') query.status = status
  return query
}

export function buildTaskSummary(task, detail = null) {
  const latestRun = detail?.latest_run || null
  const status = getTaskStatusMeta(task, latestRun)
  const scope = task?.scope || {}
  const scopeParts = []
  const researchType = scope.research_type || task?.research_type || ''
  if (researchType) scopeParts.push(RESEARCH_TYPE_LABELS[researchType] || researchType)
  scopeParts.push(scope.report_depth || 'standard', scope.time_range || 'last_12_months')

  return {
    id: task?.id,
    title: task?.title || '未命名研究任务',
    scope: scopeParts.join(' · '),
    status: status.label,
    statusTone: status.tone,
    statusReason: status.reason,
    statusDescription: status.description,
    evidenceCount: countItems(detail?.evidence),
    claimCount: countItems(detail?.claims),
    coverage: latestReportCoverage(detail),
    updatedAt: task?.updated_at || '',
    rawStatus: task?.status || 'draft',
    canRetry: status.canRetry,
    canResume: status.canResume,
    canCancel: status.canCancel,
  }
}

export function buildTaskSummaries(tasks = [], detailsById = {}) {
  return tasks.map((task) => buildTaskSummary(task, detailsById[task.id] || null))
}

export function getAvailableTaskActions(task, latestRun = null) {
  const meta = getTaskStatusMeta(task, latestRun)
  return {
    canOpen: true,
    canRetry: meta.canRetry,
    canResume: meta.canResume,
    canCancel: meta.canCancel,
  }
}

export function buildTaskRecoveryFeedback(task, latestRun = null) {
  const meta = getTaskStatusMeta(task, latestRun)
  const reason = meta.reason || '暂无详细原因'
  if (meta.canResume) {
    return {
      tone: 'failed',
      title: '可以从失败节点继续执行',
      description: reason,
      primaryAction: 'resume',
    }
  }
  if (meta.canRetry) {
    return {
      tone: meta.rawStatus === 'canceled' ? 'canceled' : 'failed',
      title: meta.rawStatus === 'canceled' ? '任务已取消，可以重新发起' : '任务失败，可以重新运行',
      description: reason,
      primaryAction: 'retry',
    }
  }
  if (meta.canCancel) {
    return {
      tone: 'active',
      title: '任务正在执行，可以按需取消',
      description: meta.description,
      primaryAction: 'cancel',
    }
  }
  return null
}

export function getRunHistory(runs = [], currentRunId = '') {
  return [...runs]
    .sort((left, right) => {
      const leftTime = new Date(left.started_at || left.queued_at || 0).getTime()
      const rightTime = new Date(right.started_at || right.queued_at || 0).getTime()
      return rightTime - leftTime
    })
    .map((run) => {
      const isCurrent = Boolean(currentRunId && run.id === currentRunId)
      return {
        ...run,
        isCurrent,
        label: isCurrent ? '当前 run' : '历史 run',
        statusLabel: RUN_STATUS_LABELS[run.status] || run.status,
        reason: run.error_message || '',
      }
    })
}
