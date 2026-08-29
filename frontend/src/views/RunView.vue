<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AlertTriangle, ArrowRight, Check, ExternalLink, FileText, ListChecks, Pause, RefreshCcw, X } from 'lucide-vue-next'
import { useTasksStore } from '@/stores/tasks'
import { buildAuditEvents, buildResearchTimeline, buildResearchWorkbenchSummary, formatDuration } from '@/lib/timeline'
import { buildEvidenceFilterOptions, buildEvidenceTraceState, buildEvidenceViewModel, buildEvidenceWallItems, filterEvidenceViewModels, sourceTypeLabel, type EvidenceViewModel } from '@/lib/evidence'
import { buildClaimEvidenceGroups } from '@/lib/review'

const router = useRouter()
const route = useRoute()
const tasksStore = useTasksStore()

const taskDetail = computed(() => tasksStore.taskDetail)
const isLoading = computed(() => tasksStore.isLoading)
const selectedEvidenceId = ref<number | null>(null)

const currentTaskTitle = computed(() => taskDetail.value?.task.title || '研究任务')
const evidenceCount = computed(() => taskDetail.value?.evidence?.length || 0)
const claimCount = computed(() => taskDetail.value?.claims?.length || 0)

const researchTimeline = computed(() => {
  return buildResearchTimeline(tasksStore.taskEvents, taskDetail.value?.latest_run)
})
const workbenchSummary = computed(() => buildResearchWorkbenchSummary(
  tasksStore.taskEvents,
  { evidenceCount: evidenceCount.value, claimCount: claimCount.value },
  taskDetail.value?.latest_run,
))
const citationCoverage = computed(() => Math.round((tasksStore.taskDetail?.reports?.at(-1)?.citation_coverage ?? 0) * 100))
const latestReport = computed(() => taskDetail.value?.reports?.at(-1) || null)
const reportDraftSections = computed(() => {
  return (latestReport.value?.sections || []).map((section) => ({
    id: section.id,
    title: section.title,
    evidenceCount: section.evidence?.length || 0,
    excerpt: (section.content_markdown || '')
      .replace(/\s*(?:Evidence|证据)\s*[:：]\s*[0-9,\s、]+/g, '')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 360),
  }))
})
const timelineStatusCards = computed(() => [
  { label: '证据', value: evidenceCount.value },
  { label: 'Claim', value: claimCount.value },
  { label: '覆盖率', value: `${citationCoverage.value}%` },
])
const timelineStatusNote = computed(() => {
  if (!researchTimeline.value.length) return '暂无节点事件'
  const current = researchTimeline.value.find((item) => item.status === 'started' || item.status === 'retrying')
  return current?.summary || workbenchSummary.value.currentStageLabel || '研究进行中'
})

function timelineStatusClass(status: string) {
  return `node-${status}`
}

const canResumeCurrentTask = computed(() => {
  return taskDetail.value?.task.status === 'failed'
})

const auditEvents = computed(() => buildAuditEvents(tasksStore.taskEvents).slice().reverse())
const claims = computed(() => taskDetail.value?.claims || [])
const evidenceWallItems = computed(() => {
  const claimsValue = taskDetail.value?.claims || []
  const rawItems = (taskDetail.value?.evidence || []).map((evidence) => {
    const boundClaimCount = claimsValue.filter((claim) => claim.evidence_ids.includes(evidence.id)).length
    return buildEvidenceViewModel(evidence, boundClaimCount)
  })
  return buildEvidenceWallItems(rawItems, claimsValue)
})
const evidenceItems = computed(() => {
  return filterEvidenceViewModels(evidenceWallItems.value, {
    sourceType: tasksStore.evidenceSourceTypeFilter,
    competitor: tasksStore.evidenceCompetitorFilter,
    dimension: tasksStore.evidenceDimensionFilter,
  })
})
const evidenceFilterOptions = computed(() => buildEvidenceFilterOptions(evidenceWallItems.value))
const sourceTypeOptions = computed(() => evidenceFilterOptions.value.sourceTypes)
const competitorOptions = computed(() => evidenceFilterOptions.value.competitors)
const dimensionOptions = computed(() => evidenceFilterOptions.value.dimensions)
const highQualityEvidenceCount = computed(() => evidenceItems.value.filter((item) => item.confidence >= 80).length)
const selectedEvidence = computed(() => evidenceWallItems.value.find((item) => item.id === selectedEvidenceId.value) || null)
const selectedSnapshot = computed(() => {
  const sourceId = selectedEvidence.value?.sourceId
  return sourceId ? tasksStore.sourceSnapshots[String(sourceId)] || null : null
})
const selectedTraceState = computed(() => {
  const sourceId = selectedEvidence.value?.sourceId
  return buildEvidenceTraceState(selectedEvidence.value, selectedSnapshot.value, {
    loading: sourceId ? tasksStore.snapshotLoadingBySourceId[String(sourceId)] : false,
    error: sourceId ? tasksStore.snapshotErrorsBySourceId[String(sourceId)] : '',
  })
})

function eventClass(rawType: string) {
  if (rawType.includes('conflict')) return 'conflict'
  if (rawType.includes('evidence') || rawType.includes('source')) return 'evidence'
  if (rawType.includes('claim') || rawType.includes('verify')) return 'quality'
  if (rawType.includes('failed')) return 'failure'
  return 'info'
}

function claimEvidenceSummaries(claim: any) {
  return buildClaimEvidenceGroups(claim, evidenceWallItems.value)
    .flatMap((group) => group.items.map((item) => ({
      ...item,
      label: `${group.label} · E${item.id}`,
    })))
}

function refreshCurrentTask() {
  if (taskDetail.value) {
    tasksStore.fetchTaskDetail(taskDetail.value.task.id)
  }
}

function resumeTask() {
  if (taskDetail.value) {
    tasksStore.doResumeTask(taskDetail.value.task.id)
  }
}

function taskRoute(path: string) {
  return { path, query: taskDetail.value ? { taskId: taskDetail.value.task.id } : {} }
}

function selectEvidence(evidence: EvidenceViewModel) {
  selectedEvidenceId.value = evidence.id
  void tasksStore.fetchSourceSnapshot(evidence.sourceId).catch(() => undefined)
}

function selectEvidenceById(evidenceId: number) {
  const evidence = evidenceWallItems.value.find((item) => item.id === evidenceId)
  if (evidence) selectEvidence(evidence)
}

function routeTaskId(): number | null {
  const raw = Array.isArray(route.query.taskId) ? route.query.taskId[0] : route.query.taskId
  const taskId = Number(raw)
  return Number.isInteger(taskId) && taskId > 0 ? taskId : null
}

async function fallbackTaskId(): Promise<number | null> {
  if (tasksStore.apiTasks.length) {
    const activeTask = tasksStore.apiTasks.find((task) => ['confirmed', 'queued', 'running', 'waiting_review', 'failed'].includes(task.status))
    return (activeTask || tasksStore.apiTasks[0])?.id ?? null
  }
  try {
    await tasksStore.fetchTasks()
    const activeTask = tasksStore.apiTasks.find((task) => ['confirmed', 'queued', 'running', 'waiting_review', 'failed'].includes(task.status))
    return (activeTask || tasksStore.apiTasks[0])?.id ?? null
  } catch {
    return null
  }
}

async function loadRunContext() {
  const taskId = routeTaskId() || taskDetail.value?.task.id || tasksStore.currentTaskId || (await fallbackTaskId())
  if (!taskId) return
  const detail = await tasksStore.fetchTaskDetail(taskId).catch(() => null)
  const resolvedTaskId = detail?.task.id || taskDetail.value?.task.id || taskId
  if (tasksStore.shouldPollTask(detail || taskDetail.value)) {
    tasksStore.startLiveTaskSync(resolvedTaskId)
    return
  }
  await tasksStore.fetchTaskEvents(resolvedTaskId, true).catch(() => undefined)
}

onMounted(() => {
  void loadRunContext()
})

onBeforeUnmount(() => {
  tasksStore.stopPolling()
})
</script>

<template>
  <section class="run-page">
    <header class="task-topbar">
      <div>
        <span class="eyebrow">Running task</span>
        <h1>{{ currentTaskTitle }}</h1>
      </div>
      <div class="run-metrics">
        <span>证据 {{ evidenceCount }}</span>
        <span>Claim {{ claimCount }}</span>
        <span>覆盖率 {{ citationCoverage }}%</span>
        <button class="secondary-button compact" type="button"><Pause :size="16" /> 暂停</button>
        <button class="primary-button compact" type="button" @click="router.push(taskRoute('/review'))">进入审阅</button>
      </div>
    </header>

    <div class="workbench-grid">
      <aside class="pipeline-panel">
        <div class="panel-heading">
          <ListChecks :size="18" />
          <h2>研究时间线</h2>
        </div>
        <div class="timeline-insight-strip">
          <div v-for="card in timelineStatusCards" :key="card.label" class="timeline-insight-card">
            <span>{{ card.label }}</span>
            <strong>{{ card.value }}</strong>
          </div>
          <p>{{ timelineStatusNote }}</p>
        </div>
        <div v-if="researchTimeline.length" class="pipeline-list">
          <div v-for="step in researchTimeline" :key="step.key" class="pipeline-item" :class="timelineStatusClass(step.status)">
            <span class="step-dot">
              <Check v-if="step.status === 'succeeded'" :size="14" />
              <AlertTriangle v-else-if="step.status === 'failed'" :size="14" />
              <RefreshCcw v-else-if="step.status === 'retrying'" :size="13" />
            </span>
            <div>
              <strong>{{ step.label }}</strong>
              <small>
                <span>{{ step.statusLabel }}</span>
                <span v-if="formatDuration(step.durationMs)"> · {{ formatDuration(step.durationMs) }}</span>
              </small>
              <p v-if="step.description" class="step-desc">{{ step.description }}</p>
              <p>{{ step.summary }}</p>
              <button v-if="canResumeCurrentTask && step.status === 'failed'" class="secondary-button compact" type="button" :disabled="isLoading" @click.stop="resumeTask">
                <RefreshCcw :size="14" /> 继续执行
              </button>
            </div>
          </div>
        </div>
        <div v-else class="empty-state compact-empty">暂无节点事件，刷新后会显示 LangGraph 执行进度。</div>
      </aside>

      <section class="activity-panel">
        <section class="workbench-overview" aria-label="研究进度">
          <div class="workbench-overview-heading">
            <div>
              <span class="eyebrow">Research progress</span>
              <h2>研究进度</h2>
            </div>
            <strong>{{ workbenchSummary.progressPercent }}%</strong>
          </div>
          <div class="progress-track" aria-hidden="true">
            <span :style="{ width: `${workbenchSummary.progressPercent}%` }"></span>
          </div>
          <div class="workbench-overview-grid">
            <div>
              <span>当前阶段</span>
              <strong>{{ workbenchSummary.currentStageLabel }}</strong>
            </div>
            <div>
              <span>节点</span>
              <strong>{{ workbenchSummary.completedNodes }} / {{ workbenchSummary.totalNodes }}</strong>
            </div>
            <div>
              <span>证据</span>
              <strong>{{ workbenchSummary.evidenceCount }}</strong>
            </div>
            <div>
              <span>Claim</span>
              <strong>{{ workbenchSummary.claimCount }}</strong>
            </div>
          </div>
          <div v-if="workbenchSummary.failureReason" class="workbench-failure">
            <AlertTriangle :size="15" />
            <span>{{ workbenchSummary.failureReason }}</span>
          </div>
        </section>

        <div class="section-header">
          <div>
            <h2>报告草稿</h2>
            <small class="live-note">
              {{ reportDraftSections.length ? `v${latestReport?.version} · ${reportDraftSections.length} 个章节已同步` : '等待报告节点生成草稿' }}
            </small>
          </div>
          <button class="text-button" type="button" :disabled="!latestReport" @click="router.push(taskRoute('/report'))">
            查看全文 <ArrowRight :size="14" />
          </button>
        </div>
        <div v-if="reportDraftSections.length" class="report-draft-list">
          <article v-for="section in reportDraftSections" :key="section.id" class="report-draft-card">
            <div>
              <strong>{{ section.title }}</strong>
              <span>{{ section.evidenceCount }} 条章节证据</span>
            </div>
            <p>{{ section.excerpt || '该章节已创建，正在等待更多内容同步。' }}</p>
          </article>
        </div>
        <div v-else class="empty-state compact-empty">
          Agent 正在先沉淀来源、证据和 Claim；生成报告节点完成后，这里会自动出现章节草稿。
        </div>

        <div class="section-header">
          <div>
            <h2>可审计事件流</h2>
            <small class="live-note">{{ tasksStore.shouldPollTask() ? '正在实时同步' : '已同步至当前状态' }}</small>
          </div>
          <button class="text-button" type="button" @click="refreshCurrentTask"><RefreshCcw :size="15" /> 刷新</button>
        </div>
        <div v-if="auditEvents.length" class="event-list">
          <article v-for="(event, index) in auditEvents" :key="`${event.time}-${event.rawType}-${index}`" class="event-row" :class="eventClass(event.rawType)">
            <span>{{ event.time }}</span>
            <strong>{{ event.type }}</strong>
            <p>{{ event.text }}</p>
            <small v-if="event.detail">{{ event.detail }}</small>
          </article>
        </div>
        <div v-else class="empty-state">暂无执行事件，任务启动后会在这里显示进度。</div>

        <div class="section-header claim-header">
          <h2>结构化 Claim</h2>
          <button class="text-button" type="button" @click="router.push(taskRoute('/review'))">查看风险项 <ArrowRight :size="14" /></button>
        </div>
        <div v-if="claims.length" class="claim-grid">
          <article v-for="claim in claims" :key="claim.id" class="claim-card" :class="[claim.status]">
            <div class="claim-meta">
              <span>{{ claim.subject }} · {{ claim.dimension }}</span>
              <span>{{ claim.status }}</span>
              <span v-if="claim.review_decision">已审核</span>
            </div>
            <h3>{{ claim.display_text || claim.subject }}</h3>
            <p>{{ claim.predicate }}</p>
            <p v-if="claim.review_reason" class="review-reason-note">审核理由：{{ claim.review_reason }}</p>
            <div class="review-quality-row claim-quality-row">
              <span>置信度 {{ Math.round(claim.confidence_score * 100) }}% · {{ claim.confidence }}</span>
              <span>覆盖率 0%</span>
              <span>{{ claim.status }}</span>
              <span>{{ claim.evidence_ids?.length || 0 }} 条 Evidence</span>
            </div>
            <div class="source-compare claim-evidence-list">
              <button
                v-for="evidence in claimEvidenceSummaries(claim)"
                :key="evidence.id || evidence.label"
                class="evidence-chip"
                type="button"
                :disabled="!evidence.id"
                @click="selectEvidenceById(evidence.id)"
              >
                {{ evidence.label }}
              </button>
            </div>
          </article>
        </div>
        <div v-else class="empty-state">暂无结构化 Claim，等待研究流程生成结论。</div>
      </section>

      <aside class="evidence-panel evidence-wall-panel">
        <div class="panel-heading">
          <FileText :size="18" />
          <h2>证据墙</h2>
        </div>
        <div class="evidence-wall-summary">
          <div><strong>{{ evidenceCount }}</strong><span>当前证据</span></div>
          <div><strong>{{ highQualityEvidenceCount }}</strong><span>高质量</span></div>
          <div><strong>{{ sourceTypeOptions.length }}</strong><span>来源类型</span></div>
        </div>
        <section v-if="selectedEvidence" class="evidence-trace-panel" aria-label="证据溯源链">
          <div class="trace-panel-heading">
            <div>
              <span>E{{ selectedEvidence.id }} · Source #{{ selectedEvidence.sourceId }}</span>
              <h3>{{ selectedEvidence.title }}</h3>
            </div>
            <button class="icon-button compact" type="button" title="关闭证据详情" @click="selectedEvidenceId = null">
              <X :size="15" />
            </button>
          </div>
          <dl class="trace-meta-grid">
            <div>
              <dt>来源类型</dt>
              <dd>{{ selectedEvidence.type }}</dd>
            </div>
            <div>
              <dt>来源可靠性</dt>
              <dd>{{ selectedEvidence.reliabilityScore ?? selectedEvidence.confidence }}%</dd>
            </div>
            <div>
              <dt>证据质量</dt>
              <dd>{{ selectedEvidence.confidence }}%</dd>
            </div>
            <div>
              <dt>抓取时间</dt>
              <dd>{{ selectedEvidence.retrievedAt }}</dd>
            </div>
          </dl>
          <p class="trace-reasons">
            {{ selectedEvidence.reliabilityReasons?.length ? selectedEvidence.reliabilityReasons.join(' · ') : selectedEvidence.snapshotHint }}
          </p>
          <blockquote>{{ selectedEvidence.excerpt }}</blockquote>
          <div v-if="selectedEvidence.boundClaims?.length" class="trace-claim-list">
            <span v-for="claim in selectedEvidence.boundClaims" :key="claim.id">
              {{ claim.label }} · {{ claim.status }}
            </span>
          </div>
          <p class="snapshot-preview" :class="selectedTraceState.snapshotStatus">
            {{ selectedTraceState.snapshotText }}
          </p>
          <div class="trace-actions">
            <button class="secondary-button compact" type="button" :disabled="!selectedTraceState.canLoadSnapshot" @click="tasksStore.fetchSourceSnapshot(selectedEvidence.sourceId)">
              <RefreshCcw :size="14" /> 读取快照
            </button>
            <a v-if="selectedTraceState.canOpenSource" class="text-button trace-link" :href="selectedTraceState.sourceUrl" target="_blank" rel="noreferrer" @click.stop>
              <ExternalLink :size="14" /> 打开来源
            </a>
          </div>
        </section>
        <div class="filter-row">
          <select v-model="tasksStore.evidenceSourceTypeFilter" class="filter-select" :disabled="isLoading">
            <option value="all">全部来源类型</option>
            <option v-for="type in sourceTypeOptions" :key="type" :value="type">{{ sourceTypeLabel(type) }}</option>
          </select>
          <select v-model="tasksStore.evidenceCompetitorFilter" class="filter-select" :disabled="isLoading">
            <option value="all">全部竞品</option>
            <option v-for="competitor in competitorOptions" :key="competitor" :value="competitor">{{ competitor }}</option>
          </select>
          <select v-model="tasksStore.evidenceDimensionFilter" class="filter-select" :disabled="isLoading">
            <option value="all">全部维度</option>
            <option v-for="dimension in dimensionOptions" :key="dimension" :value="dimension">{{ dimension }}</option>
          </select>
        </div>
        <div v-if="evidenceItems.length" class="evidence-wall">
          <article
            v-for="evidence in evidenceItems"
            :key="evidence.id"
            class="evidence-wall-card"
            :class="{ selected: selectedEvidence?.id === evidence.id }"
            role="button"
            tabindex="0"
            @click="selectEvidence(evidence)"
            @keydown.enter.prevent="selectEvidence(evidence)"
          >
            <div class="evidence-card-topline">
              <span class="source-badge" :class="evidence.type">{{ evidence.type }}</span>
              <strong>{{ evidence.confidence }}%</strong>
            </div>
            <h3>{{ evidence.title }}</h3>
            <p class="evidence-wall-meta">{{ evidence.publisher }} · {{ evidence.domain }}</p>
            <div v-if="evidence.reliabilityScore !== undefined" class="evidence-reliability-row" :class="evidence.reliabilityLabel">
              <span>来源可靠性 {{ evidence.reliabilityScore }}%</span>
              <small>{{ evidence.reliabilityReasons?.slice(0, 2).join(' · ') }}</small>
            </div>
            <p v-if="evidence.reliabilityWarnings?.length" class="evidence-warning-note">
              {{ evidence.reliabilityWarnings[0] }}
            </p>
            <p class="evidence-wall-excerpt">{{ evidence.excerpt }}</p>
            <div class="evidence-wall-footer">
              <span>{{ evidence.claims }} 个 Claim</span>
              <a v-if="evidence.sourceUrl || evidence.canonicalUrl" :href="evidence.sourceUrl || evidence.canonicalUrl" target="_blank" rel="noreferrer" @click.stop>
                打开来源 <ArrowRight :size="13" />
              </a>
            </div>
          </article>
        </div>
        <div v-else class="empty-state compact-empty">
          {{ evidenceCount ? '当前筛选条件下暂无证据。' : '暂无证据，研究完成后会自动沉淀来源与引用片段。' }}
        </div>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.run-page {
  min-height: 100vh;
  background: #f4f6f5;
}

.workbench-grid {
  min-height: calc(100vh - 74px);
  display: grid;
  grid-template-columns: 230px minmax(420px, 1fr) 310px;
}

.pipeline-panel,
.activity-panel,
.evidence-panel {
  min-height: calc(100vh - 74px);
  padding: 20px;
  border-right: 1px solid #dce3df;
  background: #fbfcfb;
}

.activity-panel {
  background: #f7f9f8;
}

.workbench-overview {
  margin-bottom: 22px;
  padding: 14px;
  border: 1px solid #dfe8e3;
  border-radius: 8px;
  background: #fff;
}

.workbench-overview-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.workbench-overview-heading h2 {
  margin: 3px 0 0;
  color: #26342d;
  font-size: 16px;
}

.workbench-overview-heading > strong {
  color: #2f6f56;
  font-size: 24px;
  line-height: 1;
}

.progress-track {
  height: 7px;
  margin-top: 14px;
  overflow: hidden;
  border-radius: 999px;
  background: #e8efeb;
}

.progress-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #2f7d57;
  transition: width 0.2s ease;
}

.workbench-overview-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) repeat(3, minmax(60px, 0.7fr));
  gap: 10px;
  margin-top: 14px;
}

.workbench-overview-grid div {
  min-width: 0;
  padding-right: 10px;
  border-right: 1px solid #e5ebe7;
}

.workbench-overview-grid div:last-child {
  padding-right: 0;
  border-right: 0;
}

.workbench-overview-grid span,
.workbench-overview-grid strong {
  display: block;
}

.workbench-overview-grid span {
  color: #7a8780;
  font-size: 11px;
}

.workbench-overview-grid strong {
  margin-top: 5px;
  overflow-wrap: anywhere;
  color: #2b3b33;
  font-size: 13px;
}

.workbench-failure {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin-top: 13px;
  padding-top: 11px;
  border-top: 1px solid #f0d8d3;
  color: #9b4338;
  font-size: 12px;
  line-height: 1.45;
}

.evidence-panel {
  border-right: 0;
}

.evidence-wall {
  display: grid;
  gap: 9px;
  margin-top: 14px;
  max-height: 620px;
  overflow-y: auto;
  padding-right: 2px;
}

.evidence-wall-card {
  padding: 12px;
  border: 1px solid #dfe8e3;
  border-radius: 7px;
  background: #fff;
  transition: border-color 0.14s ease, background 0.14s ease, transform 0.14s ease;
}

.evidence-wall-card:hover {
  border-color: #9fc1ae;
  background: #f7fbf8;
  transform: translateY(-1px);
}

.evidence-wall-card.selected {
  border-color: #2f7d57;
  box-shadow: 0 0 0 1px rgba(47, 125, 87, 0.16);
}

.evidence-trace-panel {
  display: grid;
  gap: 10px;
  margin-top: 14px;
  padding: 13px;
  border: 1px solid #bfd6ca;
  border-radius: 8px;
  background: #fff;
}

.trace-panel-heading {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.trace-panel-heading div {
  min-width: 0;
}

.trace-panel-heading span {
  color: #2f6f56;
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 11px;
  font-weight: 760;
}

.trace-panel-heading h3 {
  margin: 5px 0 0;
  color: #26342d;
  font-size: 14px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.trace-meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
  margin: 0;
}

.trace-meta-grid div {
  min-width: 0;
  padding: 8px;
  border: 1px solid #e2e9e5;
  border-radius: 6px;
  background: #f8faf9;
}

.trace-meta-grid dt,
.trace-meta-grid dd {
  margin: 0;
}

.trace-meta-grid dt {
  color: #78867e;
  font-size: 10.5px;
}

.trace-meta-grid dd {
  margin-top: 3px;
  color: #2f5846;
  font-size: 12px;
  font-weight: 760;
  overflow-wrap: anywhere;
}

.trace-reasons,
.snapshot-preview {
  margin: 0;
  color: #5c6b63;
  font-size: 11.5px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.evidence-trace-panel blockquote {
  margin: 0;
  padding: 10px;
  border-left: 3px solid #2f7d57;
  border-radius: 6px;
  color: #405049;
  background: #f6f8f7;
  font-size: 12px;
  line-height: 1.55;
}

.trace-claim-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.trace-claim-list span {
  padding: 3px 7px;
  border-radius: 999px;
  color: #456258;
  background: #e8f1ec;
  font-size: 10.5px;
  line-height: 1.3;
}

.snapshot-preview {
  padding: 8px;
  border-radius: 6px;
  background: #f3f6f5;
}

.snapshot-preview.available {
  background: #edf6f1;
}

.snapshot-preview.error,
.snapshot-preview.unavailable {
  color: #855f23;
  background: #fff7e4;
}

.trace-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.trace-link {
  text-decoration: none;
}

.evidence-card-topline,
.evidence-wall-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.evidence-card-topline > strong {
  color: #2f6f56;
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 12px;
}

.evidence-wall-card h3 {
  margin: 10px 0 0;
  color: #26342d;
  font-size: 13px;
  line-height: 1.4;
}

.evidence-wall-meta,
.evidence-wall-excerpt {
  overflow-wrap: anywhere;
}

.evidence-wall-meta {
  margin: 5px 0 0;
  color: #7a8780;
  font-size: 10.5px;
  line-height: 1.4;
}

.evidence-reliability-row {
  display: grid;
  gap: 3px;
  margin-top: 8px;
  padding: 7px 8px;
  border: 1px solid #dfe8e3;
  border-radius: 6px;
  background: #f8faf9;
}

.evidence-reliability-row span {
  color: #315947;
  font-size: 11px;
  font-weight: 760;
}

.evidence-reliability-row small {
  color: #77857d;
  font-size: 10.5px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.evidence-reliability-row.medium span {
  color: #8a571c;
}

.evidence-reliability-row.low span {
  color: #8f3a31;
}

.evidence-warning-note {
  margin: 7px 0 0;
  padding: 7px 8px;
  border-radius: 6px;
  color: #806020;
  background: #fff7e4;
  font-size: 11px;
  line-height: 1.45;
}

.evidence-wall-excerpt {
  display: -webkit-box;
  overflow: hidden;
  margin: 9px 0 0;
  color: #4e5f56;
  font-size: 12px;
  line-height: 1.55;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
}

.evidence-wall-footer {
  margin-top: 10px;
  color: #87938c;
  font-size: 11px;
}

.evidence-wall-footer a {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: #2f6f56;
  font-weight: 700;
  text-decoration: none;
}

.evidence-wall-footer a:hover {
  text-decoration: underline;
}

.evidence-wall-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 15px;
}

.evidence-wall-summary div {
  min-height: 58px;
  padding: 9px;
  border: 1px solid #e2e9e5;
  border-radius: 7px;
  background: #fff;
}

.evidence-wall-summary strong,
.evidence-wall-summary span {
  display: block;
}

.evidence-wall-summary strong {
  color: #23513f;
  font-size: 19px;
  line-height: 1.1;
}

.evidence-wall-summary span {
  margin-top: 5px;
  color: #718079;
  font-size: 11px;
}

.timeline-insight-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin-top: 16px;
  padding: 12px;
  border: 1px solid #dde6e1;
  border-radius: 8px;
  background: #fff;
}

.timeline-insight-card {
  min-width: 0;
}

.timeline-insight-card span,
.timeline-insight-card strong,
.timeline-insight-strip p {
  display: block;
}

.timeline-insight-card span {
  color: #7a8780;
  font-size: 11px;
}

.timeline-insight-card strong {
  margin-top: 5px;
  color: #22312a;
  font-size: 14px;
  line-height: 1.2;
}

.timeline-insight-strip p {
  grid-column: 1 / -1;
  margin: 2px 0 0;
  color: #5d6b64;
  font-size: 11px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.pipeline-list {
  position: relative;
  display: grid;
  gap: 2px;
  margin-top: 20px;
}

.pipeline-list::before {
  content: "";
  position: absolute;
  top: 14px;
  bottom: 14px;
  left: 13px;
  width: 1px;
  background: #d8e0dc;
}

.pipeline-item {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-start;
  gap: 11px;
  min-height: 58px;
  padding-bottom: 11px;
}

.step-dot {
  flex: 0 0 auto;
  width: 27px;
  height: 27px;
  border: 1px solid #cad5cf;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #60746a;
  background: #fff;
}

.pipeline-item.node-succeeded .step-dot {
  color: #fff;
  border-color: #2f7d57;
  background: #2f7d57;
}

.pipeline-item.node-started .step-dot,
.pipeline-item.node-retrying .step-dot {
  border: 5px solid #d6e9df;
  background: #2f7d57;
}

.pipeline-item.node-failed .step-dot {
  color: #fff;
  border-color: #b4493d;
  background: #b4493d;
}

.pipeline-item.node-skipped .step-dot {
  color: #9aa6a0;
  border-color: #d9e0dc;
  background: #eef2f0;
}

.pipeline-item strong,
.pipeline-item small {
  display: block;
}

.pipeline-item strong {
  color: #4d5c55;
  font-size: 13px;
  line-height: 1.35;
}

.pipeline-item.node-started strong,
.pipeline-item.node-retrying strong {
  color: #1f4d39;
}

.pipeline-item.node-failed strong {
  color: #883328;
}

.pipeline-item small {
  margin-top: 3px;
  color: #8c9992;
  font-size: 11px;
}

.pipeline-item p {
  margin: 5px 0 0;
  color: #65736c;
  font-size: 11px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.pipeline-item p.step-desc {
  margin-top: 3px;
  color: #97a39d;
  font-size: 10.5px;
}

.pipeline-item.node-failed p {
  color: #9b4338;
}

.event-list {
  display: grid;
  gap: 9px;
}

.report-draft-list {
  display: grid;
  gap: 10px;
  margin-bottom: 22px;
}

.report-draft-card {
  padding: 14px;
  border: 1px solid #dfe8e3;
  border-radius: 8px;
  background: #fff;
}

.report-draft-card div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.report-draft-card strong {
  min-width: 0;
  color: #26342d;
  font-size: 14px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.report-draft-card span {
  flex: 0 0 auto;
  color: #2f6f56;
  font-size: 11px;
  font-weight: 700;
}

.report-draft-card p {
  display: -webkit-box;
  overflow: hidden;
  margin: 9px 0 0;
  color: #526059;
  font-size: 13px;
  line-height: 1.65;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
}

.live-note {
  display: block;
  margin-top: 4px;
  color: #2f7d57;
  font-size: 11px;
}

.event-row {
  min-height: 66px;
  padding: 12px 14px;
  border: 1px solid #e0e7e3;
  border-left: 3px solid #567b94;
  border-radius: 7px;
  display: grid;
  grid-template-columns: 42px 48px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  background: #fff;
}

.event-row span {
  color: #84908a;
  font-size: 11px;
}

.event-row strong {
  color: #3d5362;
  font-size: 12px;
}

.event-row p {
  margin: 0;
  color: #526059;
  font-size: 13px;
  line-height: 1.55;
}

.event-row small {
  color: #7b8882;
  font-size: 11px;
  line-height: 1.4;
}

.event-row.evidence {
  border-left-color: #2f7d57;
}

.event-row.conflict {
  border-left-color: #b7791f;
}

.event-row.info {
  border-left-color: #87918c;
}

.event-row.quality {
  border-left-color: #74658f;
}

.event-row.failure {
  border-left-color: #b4493d;
}

.claim-header {
  margin-top: 26px;
}

.claim-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.claim-card {
  min-height: 184px;
  padding: 15px;
  border: 1px solid #dfe6e2;
  border-top: 3px solid #2f7d57;
  border-radius: 8px;
  background: #fff;
}

.claim-card.存在冲突 {
  border-top-color: #b7791f;
}

.claim-card.未披露 {
  border-top-color: #87918c;
}

.claim-card.低置信度,
.claim-card.待补证 {
  border-top-color: #3b6f8f;
}

.claim-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #738079;
  font-size: 11px;
}

.claim-meta span:nth-child(3) {
  padding: 2px 6px;
  border-radius: 999px;
  color: #2f684c;
  background: #e8f3ed;
}

.claim-card h3 {
  margin: 10px 0 0;
  color: #26342d;
  font-size: 14px;
  line-height: 1.45;
}

.claim-card p {
  margin: 8px 0 0;
  color: #65726b;
  font-size: 12px;
  line-height: 1.55;
}

.claim-card .review-reason-note {
  padding: 8px 9px;
  border-radius: 7px;
  background: #f4f8f5;
  color: #4d6256;
}

.evidence-links {
  display: flex;
  gap: 6px;
  margin-top: 12px;
}

.evidence-links button {
  min-height: 26px;
  padding: 0 7px;
  border: 0;
  border-radius: 5px;
  color: #2f6f56;
  background: #e7f0ec;
  font-size: 11px;
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 15px;
}

.filter-select {
  min-width: 0;
  flex: 1 1 96px;
  height: 30px;
  padding: 0 8px;
  border: 1px solid #dbe4df;
  border-radius: 6px;
  color: #40524a;
  background: #fff;
  font: inherit;
  font-size: 12px;
}

@media (max-width: 1180px) {
  .workbench-grid {
    grid-template-columns: 210px minmax(0, 1fr);
  }

  .evidence-panel {
    grid-column: 1 / -1;
    min-height: auto;
    border-top: 1px solid #dce3df;
  }
}

@media (max-width: 820px) {
  .workbench-grid {
    grid-template-columns: 1fr;
  }

  .workbench-overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .workbench-overview-grid div:nth-child(2) {
    padding-right: 0;
    border-right: 0;
  }

  .timeline-insight-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .pipeline-panel,
  .activity-panel,
  .evidence-panel {
    min-height: auto;
    border-right: 0;
    border-bottom: 1px solid #dce3df;
  }
}
</style>
