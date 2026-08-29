<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowRight,
  BookOpen,
  ChevronLeft,
  Download,
  ExternalLink,
  Quote,
  RefreshCcw,
  Share2,
} from 'lucide-vue-next'
import { useTasksStore } from '@/stores/tasks'
import { useUiStore } from '@/stores/ui'
import {
  buildReportExportFilename,
} from '@/lib/reportExport'
import {
  buildPostReviewReportUpdateState,
  buildReportSectionEvidenceItems,
  buildReportVersionItems,
  renderMarkdownBlocks,
  type MarkdownBlock,
  type ReportSectionEvidenceItem,
} from '@/lib/reports'
import { buildEvidenceTraceState } from '@/lib/evidence'
import { exportReport, exportReportArtifact, regenerateReport } from '@/api/research'

const tasksStore = useTasksStore()
const uiStore = useUiStore()
const route = useRoute()
const router = useRouter()

const taskDetail = computed(() => tasksStore.taskDetail)
const selectedReportVersion = computed(() => tasksStore.selectedReportVersion)

const currentTaskTitle = computed(() => taskDetail.value?.task.title || '研究报告')

const activeReport = computed(() => {
  const reports = taskDetail.value?.reports || []
  if (!reports.length) return null
  if (selectedReportVersion.value) {
    return reports.find(r => r.version === selectedReportVersion.value) || reports[reports.length - 1]
  }
  return reports[reports.length - 1]
})

const reportVersionItems = computed(() => buildReportVersionItems(taskDetail.value?.reports || []))

const postReviewReportUpdate = computed(() =>
  buildPostReviewReportUpdateState(taskDetail.value?.reports || [], selectedReportVersion.value),
)

type SectionEntry = {
  section: { id: number; title: string; content_markdown: string; evidence?: unknown[] }
  blocks: MarkdownBlock[]
  evidenceItems: ReportSectionEvidenceItem[]
}

const sectionEntries = computed<SectionEntry[]>(() => {
  const sections = (activeReport.value?.sections || []) as Array<{
    id: number
    title: string
    content_markdown: string
    evidence?: unknown[]
  }>
  return sections.map(section => ({
    section,
    blocks: renderMarkdownBlocks(section.content_markdown || ''),
    evidenceItems: buildReportSectionEvidenceItems(section as never),
  }))
})

const citationCoverage = computed(() =>
  Math.round((activeReport.value?.citation_coverage ?? 0) * 100),
)

// 证据库：跨章节去重汇总全部引用证据，展示在右栏
const libraryEvidenceItems = computed<ReportSectionEvidenceItem[]>(() => {
  const seen = new Set<number>()
  const items: ReportSectionEvidenceItem[] = []
  for (const entry of sectionEntries.value) {
    for (const item of entry.evidenceItems) {
      if (seen.has(item.id)) continue
      seen.add(item.id)
      items.push(item)
    }
  }
  return items
})

const SOURCE_TYPE_LABELS: Record<string, string> = {
  official: '官方',
  docs: '文档',
  news: '新闻',
  report: '报告',
  community: '社区',
  social: '社区',
}

function sourceTypeLabel(sourceType: string): string {
  return SOURCE_TYPE_LABELS[sourceType] || sourceType || '来源'
}

const activeSectionId = ref<number | null>(null)
const selectedEvidence = ref<ReportSectionEvidenceItem | null>(null)
const shareFeedback = ref('')
const readerMainEl = ref<HTMLElement | null>(null)
const progressPercent = ref(0)

function loadSnapshot() {
  if (selectedEvidence.value?.sourceId) {
    void tasksStore.fetchSourceSnapshot(selectedEvidence.value.sourceId).catch(() => undefined)
  }
}

const selectedSnapshotKey = computed(() => String(selectedEvidence.value?.sourceId ?? ''))

const selectedTraceState = computed(() =>
  buildEvidenceTraceState(
    selectedEvidence.value
      ? {
          sourceId: selectedEvidence.value.sourceId,
          sourceUrl: selectedEvidence.value.sourceUrl,
          canonicalUrl: '',
          snapshotHint: selectedEvidence.value.contentHash ? `内容哈希 ${selectedEvidence.value.contentHash}` : '',
        }
      : null,
    tasksStore.sourceSnapshots[selectedSnapshotKey.value],
    {
      loading: Boolean(tasksStore.snapshotLoadingBySourceId[selectedSnapshotKey.value]),
      error: tasksStore.snapshotErrorsBySourceId[selectedSnapshotKey.value] || '',
    },
  ),
)

function selectReportVersion(version: number) {
  tasksStore.selectedReportVersion = version
  selectedEvidence.value = null
}

function onVersionChange(event: Event) {
  selectReportVersion(Number((event.target as HTMLSelectElement).value))
}

function viewLatestPostReviewReport() {
  const reports = taskDetail.value?.reports || []
  if (reports.length) {
    tasksStore.selectedReportVersion = reports[reports.length - 1].version
  }
}

function goBack() {
  const state = window.history.state
  if (state && state.back) {
    router.back()
  } else {
    void router.push({ name: 'research' })
  }
}

function scrollToSection(sectionId: number) {
  activeSectionId.value = sectionId
  const target = document.getElementById(`report-section-${sectionId}`)
  target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// 中栏滚动时同步阅读进度与左侧目录高亮
function onReaderScroll() {
  const el = readerMainEl.value
  if (!el) return
  const max = el.scrollHeight - el.clientHeight
  progressPercent.value = max > 0 ? Math.min(100, Math.max(0, Math.round((el.scrollTop / max) * 100))) : 0

  const mainTop = el.getBoundingClientRect().top
  let current: number | null = sectionEntries.value.length ? sectionEntries.value[0].section.id : null
  for (const entry of sectionEntries.value) {
    const node = document.getElementById(`report-section-${entry.section.id}`)
    if (node && node.getBoundingClientRect().top - mainTop <= 168) {
      current = entry.section.id
    }
  }
  activeSectionId.value = current
}

function selectEvidence(evidenceId: number) {
  selectedEvidence.value = libraryEvidenceItems.value.find(item => item.id === evidenceId) || null
  if (selectedEvidence.value) {
    document.getElementById(`evidence-card-${evidenceId}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }
}

function toggleEvidence(evidence: ReportSectionEvidenceItem) {
  selectedEvidence.value = selectedEvidence.value?.id === evidence.id ? null : evidence
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

async function exportCurrentReport(format: string) {
  const report = activeReport.value
  if (!report) return
  uiStore.isExporting = true
  try {
    const filename = buildReportExportFilename(currentTaskTitle.value, format)
    if (format === 'markdown') {
      const { content } = await exportReport(report.id, 'markdown')
      downloadBlob(new Blob([content], { type: 'text/markdown;charset=utf-8' }), filename)
    } else {
      const blob = await exportReportArtifact(report.id, format as 'pdf' | 'docx')
      downloadBlob(blob, filename)
    }
  } finally {
    uiStore.isExporting = false
  }
}

async function regenerateCurrentReport() {
  const taskId = taskDetail.value?.task.id
  if (!taskId) return
  uiStore.isRegeneratingReport = true
  try {
    await regenerateReport(taskId)
    await tasksStore.fetchTaskDetail(taskId)
    const reports = taskDetail.value?.reports || []
    if (reports.length) {
      tasksStore.selectedReportVersion = reports[reports.length - 1].version
    }
  } finally {
    uiStore.isRegeneratingReport = false
  }
}

async function shareCurrentReport() {
  try {
    await navigator.clipboard.writeText(window.location.href)
    shareFeedback.value = '链接已复制'
  } catch {
    shareFeedback.value = '复制失败，请手动复制地址栏链接'
  }
  setTimeout(() => { shareFeedback.value = '' }, 2400)
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
  <section class="report-page">
    <div v-if="postReviewReportUpdate.hasPostReviewUpdate" class="report-update-banner">
      <div><span>{{ postReviewReportUpdate.message }}</span></div>
      <button
        v-if="!postReviewReportUpdate.isViewingLatest"
        class="secondary-button compact"
        type="button"
        @click="viewLatestPostReviewReport"
      >
        <ArrowRight :size="15" /> {{ postReviewReportUpdate.actionLabel }}
      </button>
    </div>

    <div class="reader-grid">
      <aside class="reader-side">
        <button class="back-button" type="button" @click="goBack">
          <ChevronLeft :size="17" />
          <span>返回目录</span>
        </button>

        <div class="side-progress">
          <div class="progress-head">
            <span>阅读进度</span>
            <em>{{ progressPercent }}%</em>
          </div>
          <div class="progress-track"><i :style="{ width: `${progressPercent}%` }"></i></div>
        </div>

        <nav v-if="sectionEntries.length" class="chapter-list" aria-label="报告目录">
          <span class="side-label">报告目录</span>
          <button
            v-for="(entry, index) in sectionEntries"
            :key="entry.section.id"
            class="chapter-item"
            :class="{ active: activeSectionId === entry.section.id }"
            type="button"
            @click="scrollToSection(entry.section.id)"
          >
            <i class="chapter-num">{{ index + 1 }}</i>
            <span>{{ entry.section.title }}</span>
          </button>
        </nav>
      </aside>

      <main ref="readerMainEl" class="reader-main" @scroll.passive="onReaderScroll">
        <template v-if="sectionEntries.length">
          <header class="reader-head">
            <span class="reader-eyebrow">研究报告 · v{{ activeReport?.version }} · 引用覆盖 {{ citationCoverage }}%</span>
            <h1>{{ currentTaskTitle }}</h1>
            <div class="reader-meta">
              <label v-if="reportVersionItems.length > 1" class="version-picker">
                <span>版本</span>
                <select :value="activeReport?.version" @change="onVersionChange">
                  <option v-for="report in reportVersionItems" :key="report.id" :value="report.version">
                    {{ report.label }}{{ report.isLatest ? ' · 最新' : '' }}
                  </option>
                </select>
              </label>
              <div class="reader-actions">
                <button class="ghost-action" type="button" @click="shareCurrentReport">
                  <Share2 :size="15" /> {{ shareFeedback || '分享' }}
                </button>
                <button
                  class="ghost-action"
                  type="button"
                  :disabled="!activeReport || uiStore.isRegeneratingReport"
                  @click="regenerateCurrentReport"
                >
                  <RefreshCcw :size="15" /> {{ uiStore.isRegeneratingReport ? '生成中' : '重新生成' }}
                </button>
                <button class="ghost-action" type="button" :disabled="!activeReport || uiStore.isExporting" @click="exportCurrentReport('markdown')">
                  <Download :size="15" /> {{ uiStore.isExporting ? '导出中' : 'Markdown' }}
                </button>
                <button class="ghost-action" type="button" :disabled="!activeReport || uiStore.isExporting" @click="exportCurrentReport('pdf')">
                  <Download :size="15" /> PDF
                </button>
                <button class="ghost-action" type="button" :disabled="!activeReport || uiStore.isExporting" @click="exportCurrentReport('docx')">
                  <Download :size="15" /> Word
                </button>
              </div>
            </div>
          </header>

          <article class="report-document">
            <section
              v-for="(entry, index) in sectionEntries"
              :id="`report-section-${entry.section.id}`"
              :key="entry.section.id"
              class="report-section"
            >
              <h3 class="section-heading">
                <i class="section-index">{{ index + 1 }}</i>
                <span>{{ entry.section.title }}</span>
              </h3>

              <template v-for="(block, blockIndex) in entry.blocks" :key="blockIndex">
                <p v-if="block.kind === 'paragraph'" class="doc-paragraph">
                  <template v-for="(token, tokenIndex) in block.inlines" :key="tokenIndex">
                    <strong v-if="token.kind === 'strong'">{{ token.text }}</strong>
                    <code v-else-if="token.kind === 'code'">{{ token.text }}</code>
                    <template v-else>{{ token.text }}</template>
                  </template>
                  <span v-if="block.citations.length" class="citation-badges">
                    <button v-for="cid in block.citations" :key="cid" class="citation" type="button" title="在证据库中查看" @click="selectEvidence(cid)">E{{ cid }}</button>
                  </span>
                </p>

                <ul v-else-if="block.kind === 'list'" class="doc-list">
                  <li v-for="(item, itemIndex) in block.items" :key="itemIndex">
                    <p>
                      <template v-for="(token, tokenIndex) in item.inlines" :key="tokenIndex">
                        <strong v-if="token.kind === 'strong'">{{ token.text }}</strong>
                        <code v-else-if="token.kind === 'code'">{{ token.text }}</code>
                        <template v-else>{{ token.text }}</template>
                      </template>
                    </p>
                    <span v-if="item.citations.length" class="citation-badges">
                      <button v-for="cid in item.citations" :key="cid" class="citation" type="button" title="在证据库中查看" @click="selectEvidence(cid)">E{{ cid }}</button>
                    </span>
                  </li>
                </ul>
              </template>
            </section>
          </article>
        </template>

        <div v-else class="empty-report">
          <BookOpen :size="34" />
          <h2>{{ taskDetail ? '暂无报告' : '未选择任务' }}</h2>
          <p>
            {{ taskDetail ? '任务还没有生成报告，完成研究流程后会在这里展示。' : '从「我的调研」列表选择一个任务，即可查看带引用的研究报告。' }}
          </p>
        </div>
      </main>

      <aside class="evidence-library" aria-label="证据库">
        <div class="library-header">
          <Quote :size="16" />
          <strong>证据库</strong>
          <span class="library-count">{{ libraryEvidenceItems.length }}</span>
        </div>
        <p v-if="!libraryEvidenceItems.length" class="empty-state">报告生成后会在这里汇总全部引用证据。</p>
        <div
          v-for="evidence in libraryEvidenceItems"
          :id="`evidence-card-${evidence.id}`"
          :key="evidence.id"
          class="evidence-card"
          :class="{ selected: selectedEvidence?.id === evidence.id }"
          role="button"
          tabindex="0"
          @click="toggleEvidence(evidence)"
          @keydown.enter.prevent="toggleEvidence(evidence)"
        >
          <div class="evidence-card-top">
            <span class="source-type-badge" :class="evidence.sourceType || 'unknown'">{{ sourceTypeLabel(evidence.sourceType) }}</span>
            <span class="evidence-num">#{{ evidence.id }}</span>
            <span v-if="evidence.reliabilityPercent != null" class="evidence-reliability">可信度 {{ evidence.reliabilityPercent }}</span>
          </div>
          <strong class="evidence-card-title">{{ evidence.sourceLabel }}</strong>
          <p class="evidence-card-quote">{{ evidence.quote || '（无引文摘要）' }}</p>

          <div v-if="selectedEvidence?.id === evidence.id" class="evidence-card-detail" @click.stop>
            <a v-if="evidence.sourceUrl" class="source-badge" :href="evidence.sourceUrl" target="_blank" rel="noreferrer">
              <ExternalLink :size="14" /> 打开来源页面
            </a>
            <div class="detail-block">
              <h3>证据质量</h3>
              <div class="quality-row">
                <div class="quality-track"><i :style="{ width: evidence.qualityLabel }"></i></div>
                <span>{{ evidence.qualityLabel }}</span>
              </div>
              <span class="claim-hint">{{ evidence.claimLabel }} 依赖此证据</span>
            </div>
            <div v-if="evidence.reliabilityPercent != null" class="detail-block">
              <h3>来源可靠性</h3>
              <div class="quality-row">
                <span class="reliability-level" :class="evidence.reliabilityLabel">{{ evidence.reliabilityLabel }}</span>
                <div class="quality-track"><i :style="{ width: `${evidence.reliabilityPercent}%` }"></i></div>
                <span>{{ evidence.reliabilityPercent }}%</span>
              </div>
              <p v-if="evidence.reliabilityReasons.length" class="reliability-reasons">
                {{ evidence.reliabilityReasons.join(' · ') }}
              </p>
            </div>
            <div class="detail-block">
              <h3>溯源信息</h3>
              <dl class="trace-meta">
                <div>
                  <dt>来源类型</dt>
                  <dd>{{ evidence.sourceType || '未知' }}</dd>
                </div>
                <div v-if="evidence.locatorText">
                  <dt>引文定位</dt>
                  <dd>{{ evidence.locatorText }}</dd>
                </div>
                <div>
                  <dt>快照状态</dt>
                  <dd>{{ evidence.snapshotAvailable ? '已存证' : '未存证' }}</dd>
                </div>
                <div v-if="evidence.contentHash">
                  <dt>内容哈希</dt>
                  <dd><code>{{ evidence.contentHash }}</code></dd>
                </div>
              </dl>
              <p class="snapshot-preview" :class="selectedTraceState.snapshotStatus">{{ selectedTraceState.snapshotText }}</p>
              <div class="trace-actions">
                <button class="secondary-button compact" type="button" :disabled="!selectedTraceState.canLoadSnapshot" @click="loadSnapshot">
                  <RefreshCcw :size="14" /> 读取快照
                </button>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.report-page {
  --ink: #1f2b25;
  --ink-soft: #4d5c55;
  --muted: #7a8780;
  --line: #e4ebe7;
  --brand: #2f6f56;
  --brand-ink: #23513f;
  --paper: #ffffff;
  --mono: "Cascadia Mono", Consolas, "JetBrains Mono", monospace;
  --serif-display: "Noto Serif SC", "Source Han Serif SC", "Songti SC", Georgia, "SimSun", serif;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f2f4f3;
  color: var(--ink);
}

.report-update-banner {
  flex: none;
  min-height: 46px;
  padding: 9px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid #d9e6de;
  background: #e7f3ec;
}

.report-update-banner > div {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #23513f;
  font-size: 13px;
  font-weight: 700;
}

.reader-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 276px minmax(0, 1fr) 380px;
}

/* ---------- 左栏：返回 + 进度 + 目录 ---------- */

.reader-side {
  min-height: 0;
  overflow-y: auto;
  padding: 20px 16px 32px;
  border-right: 1px solid var(--line);
  background: #f9faf9;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.back-button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  align-self: flex-start;
  padding: 7px 14px 7px 9px;
  border: 1px solid #dbe4df;
  border-radius: 999px;
  color: #35473f;
  background: #fff;
  font-size: 13.5px;
  font-weight: 700;
  transition: border-color 0.14s ease, box-shadow 0.14s ease, transform 0.14s ease;
}

.back-button:hover {
  border-color: #b9d2c5;
  box-shadow: 0 2px 8px rgba(47, 111, 86, 0.12);
  transform: translateX(-1px);
}

.side-progress {
  display: grid;
  gap: 8px;
}

.progress-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  color: #6c7a72;
  font-size: 12px;
  font-weight: 700;
}

.progress-head em {
  color: var(--brand-ink);
  font-family: var(--mono);
  font-size: 12px;
  font-style: normal;
}

.progress-track {
  position: relative;
  height: 5px;
  overflow: hidden;
  border-radius: 999px;
  background: #e4eae6;
}

.progress-track i {
  position: absolute;
  inset: 0 auto 0 0;
  display: block;
  border-radius: inherit;
  background: linear-gradient(90deg, #4f9a78, #2f6f56);
  transition: width 0.2s ease;
}

.side-label {
  color: #8a968f;
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.chapter-list {
  display: grid;
  gap: 3px;
}

.chapter-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 0;
  border-radius: 9px;
  color: #55645c;
  background: transparent;
  text-align: left;
  font-size: 13px;
  line-height: 1.45;
  transition: background 0.13s ease, color 0.13s ease;
}

.chapter-item:hover {
  color: #23362d;
  background: #edf2ef;
}

.chapter-item.active {
  color: #1d4c39;
  background: #e0efe7;
  font-weight: 700;
}

.chapter-num {
  flex: none;
  display: grid;
  place-items: center;
  width: 23px;
  height: 23px;
  border-radius: 50%;
  color: #6d7c74;
  background: #e8ede9;
  font-family: var(--mono);
  font-size: 11px;
  font-style: normal;
  font-weight: 700;
  transition: background 0.13s ease, color 0.13s ease;
}

.chapter-item.active .chapter-num {
  color: #fff;
  background: var(--brand);
}

/* ---------- 中栏：报告正文 ---------- */

.reader-main {
  min-height: 0;
  overflow-y: auto;
  scroll-behavior: smooth;
  background: var(--paper);
}

.reader-head {
  max-width: 820px;
  margin: 0 auto;
  padding: 44px 52px 0;
}

.reader-eyebrow {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 999px;
  color: var(--brand-ink);
  background: #e9f3ee;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.reader-head h1 {
  margin: 14px 0 0;
  color: var(--ink);
  font-family: var(--serif-display);
  font-size: 30px;
  font-weight: 700;
  line-height: 1.32;
}

.reader-meta {
  margin-top: 18px;
  padding: 12px 0;
  border-top: 1px solid #eceff0;
  border-bottom: 1px solid #eceff0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}

.version-picker {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: #6d7b73;
  font-size: 12.5px;
}

.version-picker select {
  min-height: 30px;
  padding: 0 8px;
  border: 1px solid #d7e0db;
  border-radius: 6px;
  color: #33443b;
  background: #fff;
  font-size: 12.5px;
}

.reader-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.ghost-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 30px;
  padding: 0 11px;
  border: 1px solid transparent;
  border-radius: 7px;
  color: #55645c;
  background: transparent;
  font-size: 12.5px;
  font-weight: 600;
  transition: background 0.13s ease, color 0.13s ease, border-color 0.13s ease;
}

.ghost-action:hover:not(:disabled) {
  color: var(--brand-ink);
  border-color: #cfe2d8;
  background: #f0f7f3;
}

.ghost-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.report-document {
  max-width: 820px;
  margin: 0 auto;
  padding: 12px 52px 96px;
}

.report-section {
  padding-top: 10px;
  scroll-margin-top: 16px;
}

.section-heading {
  margin: 36px 0 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  color: #22302a;
  font-family: var(--serif-display);
  font-size: 20px;
  font-weight: 700;
  line-height: 1.4;
}

.section-index {
  flex: none;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 9px;
  color: var(--brand-ink);
  background: #e6f1ea;
  font-family: var(--mono);
  font-size: 13px;
  font-style: normal;
  font-weight: 700;
}

.doc-paragraph {
  margin: 0 0 15px;
  color: #38463f;
  font-size: 15px;
  line-height: 1.85;
  text-align: justify;
}

.doc-list {
  margin: 4px 0 20px;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 10px;
}

.doc-list li {
  position: relative;
  padding: 11px 14px 11px 38px;
  border-radius: 11px;
  background: #f4f9f6;
}

.doc-list li::before {
  content: "✦";
  position: absolute;
  top: 11px;
  left: 15px;
  color: var(--brand);
  font-size: 13px;
}

.doc-list li p {
  margin: 0;
  color: #38463f;
  font-size: 14px;
  line-height: 1.75;
}

.doc-list strong,
.doc-paragraph strong {
  color: var(--ink);
  font-weight: 700;
}

.doc-list code,
.doc-paragraph code {
  padding: 1px 6px;
  border-radius: 4px;
  color: #4a5d52;
  background: #eef2ef;
  font-family: var(--mono);
  font-size: 0.88em;
}

.citation-badges {
  display: inline-flex;
  gap: 4px;
  margin-left: 8px;
  vertical-align: 1px;
}

.citation {
  min-height: 21px;
  padding: 0 7px;
  border: 1px solid #cde0d6;
  border-radius: 999px;
  color: var(--brand-ink);
  background: #eaf3ee;
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 700;
  transition: background 0.14s ease, border-color 0.14s ease;
}

.citation:hover {
  border-color: var(--brand);
  background: #d9ebe2;
}

/* 中栏空态 */

.empty-report {
  height: 100%;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 10px;
  padding: 48px;
  color: #93a09a;
  text-align: center;
}

.empty-report h2 {
  margin: 6px 0 0;
  color: #3c4a43;
  font-size: 20px;
}

.empty-report p {
  margin: 0;
  max-width: 420px;
  font-size: 13.5px;
  line-height: 1.7;
}

/* ---------- 右栏：证据库 ---------- */

.evidence-library {
  min-height: 0;
  overflow-y: auto;
  padding: 20px 16px 40px;
  border-left: 1px solid var(--line);
  background: #f9faf9;
  display: grid;
  align-content: start;
  gap: 10px;
}

.library-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 12px;
  color: #26342d;
  font-size: 14px;
}

.library-count {
  min-width: 22px;
  padding: 0 7px;
  border-radius: 999px;
  background: #e3f1ea;
  color: #285d43;
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 700;
  line-height: 18px;
  text-align: center;
}

.evidence-card {
  display: grid;
  gap: 7px;
  padding: 13px 14px;
  border: 1px solid #e0e8e3;
  border-radius: 11px;
  background: #fff;
  cursor: pointer;
  transition: border-color 0.14s ease, box-shadow 0.14s ease;
}

.evidence-card:hover {
  border-color: #b6d0c2;
  box-shadow: 0 3px 10px rgba(47, 111, 86, 0.09);
}

.evidence-card.selected {
  border-color: #8fbca6;
  box-shadow: 0 0 0 1px #8fbca6, 0 3px 10px rgba(47, 111, 86, 0.1);
}

.evidence-card-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.source-type-badge {
  padding: 1px 8px;
  border-radius: 5px;
  background: #eef4f0;
  color: #3f6653;
  font-size: 11px;
  font-weight: 700;
  line-height: 1.6;
}

.source-type-badge.official {
  background: #e3f1ea;
  color: #285d43;
}

.source-type-badge.news,
.source-type-badge.report {
  background: #fdf4e3;
  color: #8a651f;
}

.source-type-badge.community,
.source-type-badge.social {
  background: #edf0fb;
  color: #4a5b9b;
}

.evidence-num {
  color: #94a199;
  font-family: var(--mono);
  font-size: 11.5px;
}

.evidence-reliability {
  margin-left: auto;
  color: #4d6f60;
  font-family: var(--mono);
  font-size: 11.5px;
  font-weight: 700;
  white-space: nowrap;
}

.evidence-card-title {
  color: #26342d;
  font-size: 13px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.evidence-card-quote {
  margin: 0;
  color: #68766e;
  font-size: 12px;
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.evidence-card.selected .evidence-card-quote {
  display: block;
}

.evidence-card-detail {
  margin-top: 4px;
  padding-top: 12px;
  border-top: 1px dashed #d5e0da;
  display: grid;
  gap: 10px;
  cursor: default;
}

.detail-block {
  display: grid;
  gap: 7px;
}

.detail-block h3 {
  margin: 0;
  color: #31443a;
  font-size: 13px;
}

.source-badge {
  justify-self: start;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 7px;
  color: #fff;
  background: var(--brand);
  font-size: 12.5px;
  font-weight: 700;
  text-decoration: none;
}

.quality-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.quality-track {
  position: relative;
  flex: 1;
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: #e8efeb;
}

.quality-track i {
  position: absolute;
  inset: 0 auto 0 0;
  display: block;
  border-radius: inherit;
  background: var(--brand);
}

.quality-row span {
  color: var(--brand-ink);
  font-family: var(--mono);
  font-size: 12px;
}

.claim-hint {
  color: #6d7b73;
  font-size: 12px;
}

.reliability-level {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 32px;
  padding: 1px 8px;
  border-radius: 999px;
  background: #e3f1ea;
  color: #285d43;
  font-size: 11px;
  font-weight: 700;
  line-height: 1.5;
}

.reliability-level.low {
  background: #fdeeec;
  color: #8c3f34;
}

.reliability-level.medium {
  background: #fdf4e3;
  color: #8a651f;
}

.reliability-reasons {
  margin: 0;
  color: #6d7b73;
  font-size: 11.5px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.trace-meta {
  margin: 0;
  display: grid;
  gap: 6px;
}

.trace-meta div {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 8px;
  align-items: baseline;
}

.trace-meta dt {
  color: #7a8780;
  font-size: 11.5px;
}

.trace-meta dd {
  margin: 0;
  color: #35473f;
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.trace-meta dd code {
  padding: 1px 5px;
  border-radius: 4px;
  background: #eef2ef;
  font-family: var(--mono);
  font-size: 11px;
}

.snapshot-preview {
  margin: 0;
  padding: 8px;
  border-radius: 6px;
  color: #5c6b63;
  background: #f3f6f5;
  font-size: 11.5px;
  line-height: 1.5;
  overflow-wrap: anywhere;
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
}

.empty-state {
  margin: 0;
  color: #8a968f;
  font-size: 12.5px;
  line-height: 1.6;
}

/* ---------- 响应式 ---------- */

@media (max-width: 1280px) {
  .reader-grid {
    grid-template-columns: 240px minmax(0, 1fr) 340px;
  }
}

@media (max-width: 1080px) {
  .reader-grid {
    grid-template-columns: 232px minmax(0, 1fr);
  }

  .evidence-library {
    display: none;
  }
}

@media (max-width: 820px) {
  .reader-grid {
    grid-template-columns: 1fr;
    grid-template-rows: auto minmax(0, 1fr);
  }

  .reader-side {
    flex-direction: row;
    align-items: center;
    gap: 16px;
    overflow-x: auto;
    padding: 12px 16px;
    border-right: 0;
    border-bottom: 1px solid var(--line);
  }

  .side-progress {
    display: none;
  }

  .chapter-list {
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .chapter-list .side-label {
    display: none;
  }

  .chapter-item {
    white-space: nowrap;
  }

  .chapter-item span {
    max-width: 180px;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .reader-head,
  .report-document {
    padding-left: 24px;
    padding-right: 24px;
  }
}
</style>
