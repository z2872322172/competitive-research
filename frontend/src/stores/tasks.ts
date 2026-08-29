import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  cancelResearchTask,
  confirmResearchTask,
  createResearchTask,
  getResearchTask,
  getSourceSnapshot,
  listCompetitors,
  listResearchEvents,
  listResearchTasks,
  rerunResearchTask,
  resumeResearchTask,
  reviewClaim,
  type CompetitorProfileOut,
  type ResearchEventOut,
  type ResearchTaskOut,
  type SourceSnapshotOut,
  type TaskDetailOut,
} from '@/api'
import { authHeaders, isUnauthorizedError } from '@/lib/authSession'
import { buildEvidenceQuery } from '@/lib/evidence'
import { buildTaskListQuery } from '@/lib/tasks'
import { shouldPollResearchTask } from '@/lib/polling'
import { buildStructuredTaskPayload, type StructuredTaskPayloadInput } from '@/lib/taskDraft'

const ACTIVE_TASK_STORAGE_KEY = 'verda.activeResearchTaskId'

function readStoredTaskId(): number | null {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem(ACTIVE_TASK_STORAGE_KEY)
  const taskId = Number(raw)
  return Number.isInteger(taskId) && taskId > 0 ? taskId : null
}

function writeStoredTaskId(taskId: number | null) {
  if (typeof window === 'undefined') return
  if (taskId == null) {
    window.localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY)
    return
  }
  window.localStorage.setItem(ACTIVE_TASK_STORAGE_KEY, String(taskId))
}

export const useTasksStore = defineStore('tasks', () => {
  const apiTasks = ref<ResearchTaskOut[]>([])
  const taskDetail = ref<TaskDetailOut | null>(null)
  const taskDetailsById = ref<Record<string, TaskDetailOut>>({})
  const taskEvents = ref<ResearchEventOut[]>([])
  const competitorProfiles = ref<CompetitorProfileOut[]>([])
  const sourceSnapshots = ref<Record<string, SourceSnapshotOut>>({})
  const snapshotLoadingBySourceId = ref<Record<string, boolean>>({})
  const snapshotErrorsBySourceId = ref<Record<string, string>>({})
  const reviewReasons = ref<Record<string, string>>({})
  const selectedReviewClaimId = ref<number | null>(null)
  const draftPrompt = ref('')
  const currentTaskId = ref<number | null>(readStoredTaskId())
  const selectedReportVersion = ref<number | null>(null)
  const taskSearch = ref('')
  const taskStatusFilter = ref('all')
  const evidenceCompetitorFilter = ref('all')
  const evidenceDimensionFilter = ref('all')
  const evidenceSourceTypeFilter = ref('all')
  const isLoading = ref(false)

  let eventPollingTimer: number | undefined
  let detailPollingTimer: number | undefined
  let eventCursor = 0
  let pollingTaskId: number | null = null
  let eventRequestInFlight = false
  let detailRequestInFlight = false

  function stopPolling() {
    if (eventPollingTimer !== undefined) window.clearInterval(eventPollingTimer)
    if (detailPollingTimer !== undefined) window.clearInterval(detailPollingTimer)
    eventPollingTimer = undefined
    detailPollingTimer = undefined
    pollingTaskId = null
    eventRequestInFlight = false
    detailRequestInFlight = false
  }

  function shouldPollTask(detail = taskDetail.value) {
    return shouldPollResearchTask(detail)
  }

  function rememberCurrentTask(taskId: number | null) {
    currentTaskId.value = taskId
    writeStoredTaskId(taskId)
  }

  async function fetchTasks() {
    const tasks = await listResearchTasks(buildTaskListQuery(taskSearch.value, taskStatusFilter.value))
    apiTasks.value = tasks
    const detailResults = await Promise.allSettled(tasks.map((task) => getResearchTask(task.id)))
    const nextDetailsById: Record<string, TaskDetailOut> = {}
    detailResults.forEach((result, index) => {
      if (result.status === 'fulfilled') nextDetailsById[tasks[index].id] = result.value
    })
    taskDetailsById.value = nextDetailsById
  }

  async function loadTasks(onUnauthorized: (message: string) => void) {
    try {
      await fetchTasks()
      useAuthStore().errorMessage = ''
    } catch (error) {
      if (isUnauthorizedError(error)) {
        if (authHeaders().Authorization) return
        onUnauthorized('后端需要登录后查看研究数据，当前展示本地原型数据。')
        return
      }
      useAuthStore().errorMessage = '后端暂未连接，当前展示本地原型数据。'
    }
  }

  async function loadCompetitors() {
    try {
      competitorProfiles.value = await listCompetitors()
    } catch {
      competitorProfiles.value = []
    }
  }

  async function fetchTaskDetail(taskId: number, options: { applyEvidenceFilters?: boolean } = {}) {
    const evidenceQuery = options.applyEvidenceFilters
      ? buildEvidenceQuery({
          competitor: evidenceCompetitorFilter.value,
          dimension: evidenceDimensionFilter.value,
          sourceType: evidenceSourceTypeFilter.value,
        })
      : ''
    const detail = await getResearchTask(taskId, evidenceQuery)
    taskDetail.value = detail
    taskDetailsById.value = { ...taskDetailsById.value, [taskId]: detail }
    rememberCurrentTask(taskId)
    return detail
  }

  async function fetchTaskEvents(taskId: number, reset = false) {
    if (eventRequestInFlight) return taskEvents.value
    eventRequestInFlight = true
    try {
      const after = reset ? 0 : eventCursor
      const events = await listResearchEvents(taskId, after)
      if (reset) {
        taskEvents.value = events
      } else if (events.length) {
        const known = new Set(taskEvents.value.map((event) => event.sequence_no))
        taskEvents.value = [...taskEvents.value, ...events.filter((event) => !known.has(event.sequence_no))]
      }
      if (taskEvents.value.length) {
        eventCursor = Math.max(...taskEvents.value.map((event) => event.sequence_no))
      }
      return taskEvents.value
    } finally {
      eventRequestInFlight = false
    }
  }

  async function fetchSourceSnapshot(sourceId: number) {
    const key = String(sourceId)
    if (sourceSnapshots.value[key] || snapshotLoadingBySourceId.value[key]) {
      return sourceSnapshots.value[key]
    }
    snapshotLoadingBySourceId.value = { ...snapshotLoadingBySourceId.value, [key]: true }
    snapshotErrorsBySourceId.value = { ...snapshotErrorsBySourceId.value, [key]: '' }
    try {
      const snapshot = await getSourceSnapshot(sourceId)
      sourceSnapshots.value = { ...sourceSnapshots.value, [key]: snapshot }
      return snapshot
    } catch (error) {
      const message = error instanceof Error ? error.message : '快照读取失败'
      snapshotErrorsBySourceId.value = { ...snapshotErrorsBySourceId.value, [key]: message }
      throw error
    } finally {
      snapshotLoadingBySourceId.value = { ...snapshotLoadingBySourceId.value, [key]: false }
    }
  }

  function startLiveTaskSync(taskId: number) {
    stopPolling()
    pollingTaskId = taskId
    eventCursor = 0
    taskEvents.value = []
    rememberCurrentTask(taskId)
    void fetchTaskEvents(taskId, true)
    eventPollingTimer = window.setInterval(() => {
      if (pollingTaskId === taskId) void fetchTaskEvents(taskId)
    }, 1000)
    detailPollingTimer = window.setInterval(async () => {
      if (pollingTaskId !== taskId || detailRequestInFlight) return
      detailRequestInFlight = true
      try {
        const detail = await fetchTaskDetail(taskId)
        if (!shouldPollResearchTask(detail)) stopPolling()
      } finally {
        detailRequestInFlight = false
      }
    }, 2000)
  }

  async function doReviewClaim(claimId: number, decision: 'accept' | 'mark_uncertain' | 'exclude' | 'continue_research', reason: string) {
    await reviewClaim(claimId, decision, reason)
    reviewReasons.value = { ...reviewReasons.value, [claimId]: '' }
    if (taskDetail.value?.task.id) {
      await fetchTaskDetail(taskDetail.value.task.id).catch(() => undefined)
    }
  }

  async function doRerunTask(taskId: number) {
    await rerunResearchTask(taskId, true)
    startLiveTaskSync(taskId)
  }

  async function doResumeTask(taskId: number) {
    await resumeResearchTask(taskId, true)
    startLiveTaskSync(taskId)
  }

  async function doCancelTask(taskId: number) {
    await cancelResearchTask(taskId, '用户在任务列表中取消')
    stopPolling()
  }

  async function startResearchTask(input: StructuredTaskPayloadInput) {
    isLoading.value = true
    try {
      const task = await createResearchTask(buildStructuredTaskPayload(input))
      await confirmResearchTask(task.id, true)
      await fetchTaskDetail(task.id).catch(() => undefined)
      startLiveTaskSync(task.id)
      draftPrompt.value = ''
      return task
    } finally {
      isLoading.value = false
    }
  }

  return {
    apiTasks,
    taskDetail,
    taskDetailsById,
    taskEvents,
    competitorProfiles,
    sourceSnapshots,
    snapshotLoadingBySourceId,
    snapshotErrorsBySourceId,
    reviewReasons,
    selectedReviewClaimId,
    draftPrompt,
    currentTaskId,
    selectedReportVersion,
    taskSearch,
    taskStatusFilter,
    evidenceCompetitorFilter,
    evidenceDimensionFilter,
    evidenceSourceTypeFilter,
    isLoading,
    stopPolling,
    shouldPollTask,
    rememberCurrentTask,
    loadTasks,
    fetchTasks,
    loadCompetitors,
    fetchTaskDetail,
    fetchTaskEvents,
    fetchSourceSnapshot,
    startLiveTaskSync,
    doReviewClaim,
    doRerunTask,
    doResumeTask,
    doCancelTask,
    startResearchTask,
  }
})

import { useAuthStore } from './auth'
