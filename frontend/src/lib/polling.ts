import type { ResearchEventOut, TaskDetailOut } from '@/api/types'

export type ResearchSyncFeedbackTone = 'info' | 'success' | 'warning' | 'error'

export type ResearchSyncFeedback = {
  tone: ResearchSyncFeedbackTone
  title: string
  description: string
  message: string
}

const ACTIVE_RUN_STATUSES = new Set(['queued', 'running'])

function errorText(error: unknown): string {
  if (error instanceof Error) return error.message
  if (typeof error === 'string') return error
  return '未知错误'
}

function taskStatus(detail: TaskDetailOut | null): string {
  return detail?.task?.status || ''
}

function latestRunStatus(detail: TaskDetailOut | null): string {
  return detail?.latest_run?.status || ''
}

function failureReason(detail: TaskDetailOut | null): string {
  return detail?.latest_run?.error_message || detail?.task?.failure_reason || '暂无详细失败原因'
}

export function shouldPollResearchTask(detail: TaskDetailOut | null = null): boolean {
  const runStatus = latestRunStatus(detail)
  if (runStatus) return ACTIVE_RUN_STATUSES.has(runStatus)
  return taskStatus(detail) === 'running' || taskStatus(detail) === 'queued'
}

export function buildResearchSyncFeedback(options: { detail?: TaskDetailOut | null; events?: ResearchEventOut[]; error?: unknown } = {}): ResearchSyncFeedback | null {
  const { detail = null, events = [], error = null } = options

  if (error) {
    const reason = errorText(error)
    return {
      tone: 'warning',
      title: '同步失败',
      description: '暂时无法获取最新任务进度，当前状态会保留。',
      message: `同步失败：${reason}。稍后自动重试。`,
    }
  }

  if (!detail) {
    return {
      tone: 'info',
      title: '暂无任务详情',
      description: '选择一个研究任务后查看执行状态。',
      message: '暂无任务详情。',
    }
  }

  const status = latestRunStatus(detail) || taskStatus(detail)
  if (status === 'failed') {
    return {
      tone: 'error',
      title: '研究执行失败',
      description: failureReason(detail),
      message: `研究执行失败：${failureReason(detail)}。可以查看失败节点后重试或继续执行。`,
    }
  }
  if (status === 'canceled') {
    return {
      tone: 'info',
      title: '任务已取消',
      description: '任务已停止，不会继续轮询。',
      message: '任务已取消。',
    }
  }
  if (status === 'waiting_review') {
    return {
      tone: 'info',
      title: '等待审核',
      description: '研究结果已生成，等待你审核 Claim。',
      message: '研究已完成，等待审核。',
    }
  }
  if (status === 'completed') {
    return {
      tone: 'success',
      title: '研究已完成',
      description: '报告和研究结果已经可以查看。',
      message: '研究已完成。',
    }
  }
  if (shouldPollResearchTask(detail) && !events.length) {
    return {
      tone: 'info',
      title: '等待执行事件',
      description: '任务状态已同步，等待 workflow 写入第一条节点事件。',
      message: '任务状态已同步，等待 workflow 写入第一条节点事件。',
    }
  }

  return null
}
