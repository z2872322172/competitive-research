<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { AlertTriangle, ArrowRight, ClipboardCheck, Eye, RefreshCcw, Search, ShieldCheck } from 'lucide-vue-next'
import { useTasksStore } from '@/stores/tasks'
import { buildEvidenceViewModel, buildEvidenceWallItems } from '@/lib/evidence'
import {
  buildClaimEvidenceGroups,
  buildLowRiskReviewCandidates,
  buildReviewItems,
  resolveReviewReason,
  selectReviewItem,
} from '@/lib/review'

const router = useRouter()
const route = useRoute()
const tasksStore = useTasksStore()

const taskDetail = computed(() => tasksStore.taskDetail)
const isLoading = computed(() => tasksStore.isLoading)

const claims = computed(() => taskDetail.value?.claims || [])
const evidenceWallItems = computed(() => {
  const claimsValue = taskDetail.value?.claims || []
  const rawItems = (taskDetail.value?.evidence || []).map((evidence) => {
    const boundClaimCount = claimsValue.filter((claim) => claim.evidence_ids.includes(evidence.id)).length
    return buildEvidenceViewModel(evidence, boundClaimCount)
  })
  return buildEvidenceWallItems(rawItems, claimsValue)
})
const citationCoverage = computed(() => {
  if (!claims.value.length) return 0
  const totalCoverage = claims.value.reduce((sum, claim) => sum + (claim.evidence_coverage ?? 0), 0)
  return Math.round((totalCoverage / claims.value.length) * 100)
})

const highConfidenceClaims = computed(() => claims.value.filter(c => c.confidence === 'high' || c.confidence_score >= 0.8))
const conflictClaims = computed(() => claims.value.filter(c => c.status === 'conflict'))
const undisclosedClaims = computed(() => claims.value.filter(c => c.status === 'undisclosed'))
const reviewItems = computed(() => buildReviewItems(claims.value, evidenceWallItems.value))
const lowRiskReviewCandidates = computed(() => buildLowRiskReviewCandidates(claims.value))

const isReviewCompleted = computed(() => {
  return reviewItems.value.length === 0
})

const hasContinueResearchRequest = computed(() => {
  return taskDetail.value?.task.status === 'waiting_review'
})

const activeReviewItem = computed(() => selectReviewItem(reviewItems.value, tasksStore.selectedReviewClaimId || ''))
const activeReviewClaim = computed(() => {
  const item = activeReviewItem.value
  if (!item?.claimId) return null
  return claims.value.find(c => c.id === item.claimId) || null
})
const activeEvidenceGroups = computed(() => {
  return activeReviewClaim.value ? buildClaimEvidenceGroups(activeReviewClaim.value, evidenceWallItems.value) : []
})

function statusClass(status: string) {
  return status
}

function reviewEvidenceSummaries(item: any) {
  return item.evidenceSummaries || []
}

function selectReviewClaim(item: any) {
  tasksStore.selectedReviewClaimId = item.claimId
}

function handleReview(item: any, decision: 'accept' | 'mark_uncertain' | 'exclude' | 'continue_research') {
  if (!item.claimId) return
  const typedReason = tasksStore.reviewReasons[item.claimId] || ''
  tasksStore.doReviewClaim(item.claimId, decision, resolveReviewReason(item, typedReason))
}

function handleBatchAcceptLowRiskClaims() {
  if (!lowRiskReviewCandidates.value.length) return
  for (const candidate of lowRiskReviewCandidates.value) {
    tasksStore.doReviewClaim(candidate.claimId, 'accept', candidate.reason)
  }
}

function continueResearch() {
  if (taskDetail.value) {
    tasksStore.doRerunTask(taskDetail.value.task.id)
  }
}

function taskRoute(path: string) {
  return { path, query: taskDetail.value ? { taskId: taskDetail.value.task.id } : {} }
}

function routeTaskId(): number | null {
  const raw = Array.isArray(route.query.taskId) ? route.query.taskId[0] : route.query.taskId
  const taskId = Number(raw)
  return Number.isInteger(taskId) && taskId > 0 ? taskId : null
}

onMounted(() => {
  const taskId = routeTaskId() || taskDetail.value?.task.id || tasksStore.currentTaskId
  if (taskId) void tasksStore.fetchTaskDetail(taskId).catch(() => undefined)
})
</script>

<template>
  <section class="content-page">
    <header class="page-topbar">
      <div>
        <span class="eyebrow">Evidence review</span>
        <h1>证据审阅</h1>
      </div>
      <div class="topbar-buttons">
        <button v-if="hasContinueResearchRequest" class="secondary-button" type="button" :disabled="isLoading" @click="continueResearch">
          <RefreshCcw :size="17" /> 继续研究
        </button>
        <button class="primary-button" type="button" :disabled="!isReviewCompleted" @click="router.push(taskRoute('/report'))">查看报告 <ArrowRight :size="17" /></button>
      </div>
    </header>

    <div class="metric-grid">
      <div><strong>{{ citationCoverage }}%</strong><span>引用覆盖率</span></div>
      <div><strong>{{ highConfidenceClaims.length }}</strong><span>高置信度结论</span></div>
      <div><strong>{{ conflictClaims.length }}</strong><span>冲突结论</span></div>
      <div><strong>{{ undisclosedClaims.length }}</strong><span>未披露项</span></div>
    </div>

    <div class="review-action-bar">
      <div>
        <strong>低风险批量处理</strong>
        <span>可接受 {{ lowRiskReviewCandidates.length }} 条已验证 Claim</span>
      </div>
      <button
        class="primary-button compact"
        type="button"
        :disabled="isLoading || !taskDetail || !lowRiskReviewCandidates.length"
        @click="handleBatchAcceptLowRiskClaims"
      >
        <ClipboardCheck :size="16" /> 批量接受
      </button>
    </div>

    <div class="review-tabs">
      <button class="active" type="button">全部</button>
      <button type="button">冲突</button>
      <button type="button">低置信度</button>
      <button type="button">未披露</button>
      <button type="button">无引用结论</button>
    </div>

    <div v-if="reviewItems.length" class="review-layout">
      <div class="review-list">
        <article
          v-for="item in reviewItems"
          :key="item.title"
          class="review-card"
          :class="[statusClass(item.kind), { selected: activeReviewItem?.claimId === item.claimId }]"
          role="button"
          tabindex="0"
          @click="selectReviewClaim(item)"
          @keydown.enter.prevent="selectReviewClaim(item)"
          @keydown.space.prevent="selectReviewClaim(item)"
        >
          <div class="review-kind">
            <AlertTriangle v-if="item.kind === '冲突'" :size="20" />
            <Search v-else-if="item.kind === '未披露'" :size="20" />
            <Eye v-else :size="20" />
            <span>{{ item.kind }}</span>
          </div>
          <div class="review-body">
            <h2>{{ item.title }}</h2>
            <p>{{ item.summary }}</p>
            <div class="review-quality-row">
              <span>置信度 {{ item.confidencePercent ?? 0 }}% · {{ item.confidenceLabel ?? '中' }}</span>
              <span>引用覆盖 {{ item.coveragePercent ?? 0 }}%</span>
              <span>{{ item.statusLabel || item.kind }}</span>
            </div>
            <div class="source-compare">
              <button
                v-for="evidence in reviewEvidenceSummaries(item)"
                :key="evidence.id || evidence.label"
                class="evidence-chip"
                type="button"
                :disabled="!evidence.id"
              >
                {{ evidence.label }}
              </button>
            </div>
            <div class="recommendation">
              <ClipboardCheck :size="17" />
              <span>{{ item.recommendation }}</span>
            </div>
            <label class="review-reason-field">
              <span>审核原因</span>
              <textarea
                v-if="item.claimId"
                v-model="tasksStore.reviewReasons[item.claimId]"
                rows="2"
                placeholder="填写接受、排除、标记不确定或继续查证的原因"
              />
            </label>
            <div class="card-actions">
              <button class="primary-button compact" type="button" :disabled="isLoading || !item.claimId" @click="handleReview(item, 'accept')">接受建议</button>
              <button class="secondary-button compact" type="button" :disabled="isLoading || !item.claimId" @click="handleReview(item, 'mark_uncertain')">标记不确定</button>
              <button class="secondary-button compact danger-button" type="button" :disabled="isLoading || !item.claimId" @click="handleReview(item, 'exclude')">排除报告</button>
              <button class="secondary-button compact" type="button" :disabled="isLoading || !item.claimId" @click="handleReview(item, 'continue_research')">继续查证</button>
            </div>
          </div>
        </article>
      </div>

      <aside v-if="activeReviewItem && activeReviewClaim" class="review-focus-panel">
        <div class="panel-heading">
          <ClipboardCheck :size="18" />
          <h2>当前聚焦 Claim</h2>
        </div>
        <div class="review-focus-header">
          <div class="review-focus-badges">
            <span class="focus-badge">{{ activeReviewItem.kind }}</span>
            <span class="focus-badge muted">{{ activeReviewClaim.status }}</span>
          </div>
          <h3>{{ activeReviewClaim.display_text || activeReviewClaim.subject }}</h3>
        <p>{{ activeReviewClaim.predicate }}</p>
      </div>

      <dl class="review-focus-metrics">
        <div>
          <dt>置信度</dt>
          <dd>{{ Math.round((activeReviewClaim.confidence_score ?? 0) * 100) }}% · {{ activeReviewClaim.confidence }}</dd>
        </div>
        <div>
          <dt>覆盖率</dt>
          <dd>{{ activeReviewItem.coveragePercent }}%</dd>
        </div>
        <div>
          <dt>状态</dt>
          <dd>{{ activeReviewClaim.status }}</dd>
        </div>
        <div>
          <dt>Evidence</dt>
          <dd>{{ activeReviewClaim.evidence_ids?.length ?? 0 }} 条</dd>
        </div>
      </dl>

        <section v-if="activeReviewItem.conflictAnalysis" class="review-focus-section conflict-analysis-panel">
          <h3>调和建议</h3>
          <p>{{ activeReviewItem.conflictAnalysis.recommendation }}</p>
          <div class="conflict-score-grid">
            <div>
              <span>支持强度</span>
              <strong>{{ Math.round(activeReviewItem.conflictAnalysis.support_score * 100) }}%</strong>
            </div>
            <div>
              <span>冲突强度</span>
              <strong>{{ Math.round(activeReviewItem.conflictAnalysis.conflict_score * 100) }}%</strong>
            </div>
          </div>
          <ul>
            <li v-for="reason in activeReviewItem.conflictAnalysis.rationale" :key="reason">{{ reason }}</li>
          </ul>
        </section>

        <section v-if="activeEvidenceGroups.length" class="review-focus-section">
          <h3>证据分组</h3>
          <div class="claim-evidence-groups">
            <div v-for="group in activeEvidenceGroups" :key="group.relation" class="claim-evidence-group" :class="group.relation">
              <strong>{{ group.label }}</strong>
              <button
                v-for="evidence in group.items"
                :key="evidence.id"
                class="evidence-chip evidence-chip-detail"
                type="button"
              >
                <span>E{{ evidence.id }} · {{ evidence.sourceTitle || evidence.label }}</span>
                <small v-if="evidence.reliabilityScore !== undefined">来源可靠性 {{ evidence.reliabilityScore }}%</small>
              </button>
            </div>
          </div>
        </section>

        <section v-if="activeReviewItem.reviewReason" class="review-focus-section">
          <h3>上次审核理由</h3>
          <p>{{ activeReviewItem.reviewReason }}</p>
        </section>

        <label class="review-reason-field">
          <span>审核原因</span>
          <textarea
            v-if="activeReviewClaim.id"
            v-model="tasksStore.reviewReasons[activeReviewClaim.id]"
            rows="3"
            placeholder="填写接受、排除、标记不确定或继续查证的原因"
          />
        </label>

        <div class="card-actions review-focus-actions">
          <button class="primary-button compact" type="button" :disabled="isLoading || !activeReviewItem.claimId" @click="handleReview(activeReviewItem, 'accept')">接受建议</button>
          <button class="secondary-button compact" type="button" :disabled="isLoading || !activeReviewItem.claimId" @click="handleReview(activeReviewItem, 'mark_uncertain')">标记不确定</button>
          <button class="secondary-button compact danger-button" type="button" :disabled="isLoading || !activeReviewItem.claimId" @click="handleReview(activeReviewItem, 'exclude')">排除报告</button>
          <button class="secondary-button compact" type="button" :disabled="isLoading || !activeReviewItem.claimId" @click="handleReview(activeReviewItem, 'continue_research')">继续查证</button>
        </div>
      </aside>
    </div>
    <div v-else class="empty-state review-complete-state">
      <ShieldCheck :size="24" />
      <span>{{ isReviewCompleted ? '暂无待审核风险项，当前报告可以交付。' : '暂无待审核风险项，当前结论已处理完毕。' }}</span>
      <button class="primary-button compact" type="button" @click="router.push(taskRoute('/report'))">查看报告</button>
    </div>
  </section>
</template>

<style scoped>
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  overflow: hidden;
  border: 1px solid #dfe6e2;
  border-radius: 8px;
  background: #fff;
}

.metric-grid div {
  min-height: 86px;
  padding: 16px;
  border-right: 1px solid #e5ebe7;
}

.metric-grid div:last-child {
  border-right: 0;
}

.metric-grid strong,
.metric-grid span {
  display: block;
}

.metric-grid strong {
  color: #23513f;
  font-size: 25px;
  line-height: 1.1;
}

.metric-grid span {
  margin-top: 8px;
  color: #6f7b75;
  font-size: 12px;
}

.review-action-bar {
  min-height: 52px;
  margin: 18px 0 8px;
  padding: 10px 12px;
  border: 1px solid #dfe6e2;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: #fbfcfb;
}

.review-action-bar > div {
  display: grid;
  gap: 3px;
}

.review-action-bar strong {
  color: #26342d;
  font-size: 14px;
}

.review-action-bar span {
  color: #69776f;
  font-size: 12px;
}

.review-tabs {
  display: flex;
  gap: 8px;
  margin: 20px 0 14px;
  overflow-x: auto;
}

.review-tabs button {
  min-height: 32px;
  padding: 0 11px;
  border: 0;
  border-radius: 6px;
  color: #64726b;
  background: transparent;
  white-space: nowrap;
  font-size: 13px;
}

.review-tabs button.active {
  color: #23513f;
  background: #e4eee9;
}

.review-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 16px;
  align-items: start;
}

.review-list {
  display: grid;
  gap: 14px;
}

.review-card {
  padding: 18px;
  display: grid;
  grid-template-columns: 96px minmax(0, 1fr);
  gap: 18px;
  cursor: pointer;
}

.review-card.selected {
  border-color: #2f7d57;
  box-shadow: 0 0 0 1px rgba(47, 125, 87, 0.16);
}

.review-kind {
  display: grid;
  place-items: center;
  align-self: start;
  min-height: 72px;
  border-radius: 7px;
  gap: 7px;
  color: #8a571c;
  background: #f7ead8;
  font-size: 13px;
  font-weight: 760;
}

.review-card.未披露 .review-kind {
  color: #59645e;
  background: #eceff0;
}

.review-card.低置信度 .review-kind {
  color: #335f79;
  background: #e4eef5;
}

.review-focus-panel {
  padding: 18px;
  border: 1px solid #dfe6e2;
  border-radius: 8px;
  background: #fff;
  position: sticky;
  top: 18px;
}

.review-focus-header {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.review-focus-header h3 {
  margin: 0;
  color: #26342d;
  font-size: 18px;
}

.review-focus-header p {
  margin: 0;
  color: #5e6c65;
  font-size: 13px;
  line-height: 1.6;
}

.review-focus-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.focus-badge {
  min-height: 28px;
  padding: 0 9px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  color: #23513f;
  background: #e4eee9;
  font-size: 12px;
  font-weight: 700;
}

.focus-badge.muted {
  color: #5a675f;
  background: #edf1ef;
}

.review-focus-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin: 14px 0 0;
}

.review-focus-metrics div {
  padding: 10px;
  border: 1px solid #e1e8e4;
  border-radius: 8px;
  background: #fbfcfb;
}

.review-focus-metrics dt {
  color: #758279;
  font-size: 11px;
}

.review-focus-metrics dd {
  margin: 4px 0 0;
  color: #244f3d;
  font-size: 15px;
  font-weight: 760;
}

.review-focus-section {
  margin-top: 14px;
}

.review-focus-section h3 {
  margin: 0 0 10px;
  color: #34463d;
  font-size: 13px;
}

.review-focus-section p {
  margin: 0;
  color: #53645a;
  font-size: 12px;
  line-height: 1.5;
}

.conflict-analysis-panel {
  padding: 12px;
  border: 1px solid #e4d9c8;
  border-radius: 8px;
  background: #fffaf0;
}

.conflict-score-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.conflict-score-grid div {
  padding: 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.72);
}

.conflict-score-grid span,
.conflict-score-grid strong {
  display: block;
}

.conflict-score-grid span {
  color: #7f725e;
  font-size: 10.5px;
}

.conflict-score-grid strong {
  margin-top: 3px;
  color: #76541c;
  font-size: 15px;
}

.conflict-analysis-panel ul {
  margin: 10px 0 0;
  padding-left: 16px;
  color: #665945;
  font-size: 11.5px;
  line-height: 1.5;
}

.claim-evidence-groups {
  display: grid;
  gap: 10px;
}

.claim-evidence-group {
  display: grid;
  gap: 7px;
}

.claim-evidence-group > strong {
  color: #315447;
  font-size: 12px;
}

.claim-evidence-group.conflicts > strong {
  color: #8a571c;
}

.evidence-chip-detail {
  min-height: auto;
  align-items: flex-start;
  flex-direction: column;
  padding: 7px 8px;
  text-align: left;
  line-height: 1.35;
}

.evidence-chip-detail span,
.evidence-chip-detail small {
  overflow-wrap: anywhere;
}

.evidence-chip-detail small {
  color: #77857d;
  font-size: 10.5px;
}

.review-focus-actions {
  margin-top: 14px;
}

.review-body h2 {
  margin: 0;
  color: #26342d;
  font-size: 17px;
}

.review-body p {
  margin: 8px 0 0;
  color: #5e6c65;
  font-size: 14px;
  line-height: 1.6;
}

.recommendation {
  gap: 7px;
  margin-top: 12px;
  color: #475c51;
  font-size: 13px;
}

.review-reason-field {
  display: grid;
  gap: 6px;
  margin-top: 12px;
  color: #65726b;
  font-size: 12px;
  font-weight: 720;
}

.review-reason-field textarea {
  width: 100%;
  min-height: 66px;
  padding: 9px;
  border: 1px solid #dfe6e2;
  border-radius: 7px;
  resize: vertical;
  color: #26342d;
  background: #fff;
  font: inherit;
  font-weight: 500;
}

.review-complete-state {
  gap: 12px;
}

@media (max-width: 820px) {
  .review-action-bar {
    align-items: flex-start;
    flex-direction: column;
  }

  .review-card {
    grid-template-columns: 1fr;
  }

  .review-layout {
    grid-template-columns: 1fr;
  }

  .review-focus-panel {
    position: static;
  }

  .review-focus-metrics {
    grid-template-columns: 1fr;
  }

  .review-kind {
    min-height: 46px;
    display: flex;
    justify-content: center;
  }
}
</style>
