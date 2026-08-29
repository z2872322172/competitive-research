<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ClipboardCheck, FileText, ListChecks, Plus, RefreshCcw, Search } from 'lucide-vue-next'
import { useTasksStore } from '@/stores/tasks'
import type { ResearchTaskOut, TaskDetailOut } from '@/api/types'

const router = useRouter()
const tasksStore = useTasksStore()

const apiTasks = computed(() => tasksStore.apiTasks)
const isLoading = computed(() => tasksStore.isLoading)

const taskStatusFilters = [
  { value: 'all', label: '全部' },
  { value: 'running', label: '进行中' },
  { value: 'waiting_review', label: '待审阅' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
]

const STATUS_META: Record<string, { label: string; cls: string }> = {
  draft: { label: '草稿', cls: 'draft' },
  running: { label: '进行中', cls: 'running' },
  waiting_review: { label: '待审阅', cls: 'waiting' },
  completed: { label: '已完成', cls: 'done' },
  failed: { label: '失败', cls: 'failed' },
  canceled: { label: '已取消', cls: 'canceled' },
}

function statusMeta(status: string) {
  return STATUS_META[status] || { label: status, cls: 'draft' }
}

function detailOf(taskId: number): TaskDetailOut | null {
  return tasksStore.taskDetailsById[taskId] || null
}

const taskRows = computed(() => {
  return apiTasks.value.map((task, index) => {
    const detail = detailOf(task.id)
    const reports = detail?.reports || []
    const latest = reports[reports.length - 1] || null
    const competitors = (task.scope?.competitors || []).filter(Boolean)
    const meta = statusMeta(task.status)
    return {
      task,
      index,
      statusLabel: meta.label,
      statusCls: meta.cls,
      hasReport: reports.length > 0,
      reportVersion: latest?.version ?? 0,
      coveragePercent: Math.round((latest?.citation_coverage ?? 0) * 100),
      evidenceCount: detail?.evidence?.length ?? 0,
      claimCount: detail?.claims?.length ?? 0,
      competitors: competitors.slice(0, 3),
      competitorOverflow: Math.max(0, competitors.length - 3),
      promptSnippet: (task.prompt || '').replace(/\s+/g, ' ').slice(0, 64),
      updatedAt: task.updated_at ? new Date(task.updated_at).toLocaleDateString() : '-',
    }
  })
})

const libraryStats = computed(() => {
  const completed = apiTasks.value.filter(t => t.status === 'completed').length
  const reportCount = apiTasks.value.reduce((sum, t) => sum + (detailOf(t.id)?.reports?.length ?? 0), 0)
  return { total: apiTasks.value.length, completed, reportCount }
})

function applyTaskFilters() {
  void tasksStore.loadTasks(() => {})
}

function clearTaskFilters() {
  tasksStore.taskSearch = ''
  tasksStore.taskStatusFilter = 'all'
  void tasksStore.loadTasks(() => {})
}

// 打开任务：先拉取详情再跳转。完成后直接进报告，进行中/失败进过程页。
async function openTask(task: ResearchTaskOut, preferred: 'report' | 'run' | 'review') {
  const hasReport = (detailOf(task.id)?.reports?.length ?? 0) > 0
  const page = preferred === 'report' && !hasReport ? 'run' : preferred
  try {
    await tasksStore.fetchTaskDetail(task.id)
  } catch {
    // 拉取失败仍然跳转，目标页会展示空状态
  }
  router.push({ path: `/${page}`, query: { taskId: task.id } })
}

function resumeTask(task: ResearchTaskOut) {
  tasksStore.doResumeTask(task.id)
}

function retryTask(task: ResearchTaskOut) {
  tasksStore.doRerunTask(task.id)
}

function cancelTask(task: ResearchTaskOut) {
  tasksStore.doCancelTask(task.id)
}
</script>

<template>
  <section class="content-page library-page">
    <header class="library-topbar">
      <div>
        <span class="eyebrow">Research library</span>
        <h1>我的调研</h1>
        <p class="library-sub">
          共 {{ libraryStats.total }} 项调研 · {{ libraryStats.completed }} 项已完成 · 沉淀 {{ libraryStats.reportCount }} 份报告
        </p>
      </div>
      <button class="primary-button" type="button" @click="router.push('/workspace')"><Plus :size="17" /> 新建任务</button>
    </header>

    <div class="library-toolbar">
      <label class="search-field">
        <Search :size="16" />
        <input v-model="tasksStore.taskSearch" type="search" placeholder="搜索任务标题或研究需求" @keyup.enter="applyTaskFilters" />
      </label>
      <div class="segmented-control">
        <button
          v-for="filter in taskStatusFilters"
          :key="filter.value"
          type="button"
          :class="{ selected: tasksStore.taskStatusFilter === filter.value }"
          @click="tasksStore.taskStatusFilter = filter.value; applyTaskFilters()"
        >
          {{ filter.label }}
        </button>
      </div>
      <button class="text-button" type="button" :disabled="isLoading" @click="applyTaskFilters"><RefreshCcw :size="15" /> 刷新</button>
      <button class="text-button muted" type="button" @click="clearTaskFilters">清空</button>
    </div>

    <div class="ledger-panel">
      <div v-if="isLoading" class="ledger-loading" aria-hidden="true"><span></span></div>

      <div class="ledger-head">
        <span class="col-index">编号</span>
        <span class="col-main">任务</span>
        <span class="col-status">状态</span>
        <span class="col-stats">证据 / Claim / 覆盖</span>
        <span class="col-date">更新</span>
        <span class="col-actions">操作</span>
      </div>

      <article
        v-for="row in taskRows"
        :key="row.task.id"
        class="ledger-row"
        :class="row.statusCls"
        :style="{ '--row-i': row.index }"
        role="button"
        tabindex="0"
        @click="openTask(row.task, 'report')"
        @keydown.enter.prevent="openTask(row.task, 'report')"
      >
        <span class="row-index">{{ String(row.index + 1).padStart(2, '0') }}</span>

        <div class="row-main">
          <h3 class="row-title">{{ row.task.title }}</h3>
          <div class="row-sub">
            <span v-if="row.competitors.length" class="row-chips">
              <em v-for="competitor in row.competitors" :key="competitor">{{ competitor }}</em>
              <em v-if="row.competitorOverflow" class="more">+{{ row.competitorOverflow }}</em>
            </span>
            <span class="row-prompt">{{ row.promptSnippet }}</span>
          </div>
        </div>

        <span class="status-stamp"><i class="stamp-dot"></i>{{ row.statusLabel }}</span>

        <div class="row-stats">
          <div class="stat-pair">
            <span><strong>{{ row.evidenceCount }}</strong> 证据</span>
            <span><strong>{{ row.claimCount }}</strong> Claim</span>
          </div>
          <div class="coverage-track">
            <i :style="{ width: row.coveragePercent + '%' }"></i>
          </div>
          <em class="coverage-note" :class="{ muted: !row.hasReport }">
            {{ row.hasReport ? `v${row.reportVersion} · 覆盖 ${row.coveragePercent}%` : '暂无报告' }}
          </em>
        </div>

        <span class="row-date">{{ row.updatedAt }}</span>

        <div class="row-actions" @click.stop>
          <button
            v-if="row.hasReport"
            class="primary-button compact"
            type="button"
            @click="openTask(row.task, 'report')"
          >
            <FileText :size="15" /> 查看报告
          </button>
          <button v-else class="secondary-button compact" type="button" @click="openTask(row.task, 'run')">
            <ListChecks :size="15" /> 查看过程
          </button>
          <button
            v-if="row.statusCls === 'waiting'"
            class="icon-button compact"
            type="button"
            title="进入证据审阅"
            @click="openTask(row.task, 'review')"
          >
            <ClipboardCheck :size="16" />
          </button>
          <button v-if="row.statusCls === 'failed'" class="secondary-button compact" type="button" @click="resumeTask(row.task)">
            <RefreshCcw :size="15" /> 继续执行
          </button>
          <button v-if="row.statusCls === 'failed'" class="text-button" type="button" @click="retryTask(row.task)">重试</button>
          <button v-if="row.statusCls === 'running'" class="text-button" type="button" @click="cancelTask(row.task)">取消</button>
        </div>
      </article>

      <div v-if="!taskRows.length && !isLoading" class="empty-state">
        暂无调研任务。从工作台输入研究需求，第一份带引用的竞品分析会出现在这里。
      </div>
    </div>
  </section>
</template>

<style scoped>
.library-page {
  --ink: #1f2b25;
  --ink-soft: #4d5c55;
  --muted: #7a8780;
  --line: #e4ebe7;
  --brand: #2f6f56;
  --brand-ink: #23513f;
  --mono: "Cascadia Mono", Consolas, "JetBrains Mono", monospace;
  --serif-display: "Noto Serif SC", "Source Han Serif SC", "Songti SC", Georgia, "SimSun", serif;
}

/* ---- 顶部 ---- */
.library-topbar {
  margin-bottom: 20px;
}

.library-topbar h1 {
  margin: 3px 0 0;
  color: var(--ink);
  font-family: var(--serif-display);
  font-size: 30px;
  font-weight: 700;
  letter-spacing: 0.01em;
  line-height: 1.2;
}

.library-sub {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 13px;
}

/* ---- 工具条 ---- */
.library-toolbar {
  display: grid;
  grid-template-columns: minmax(240px, 1fr) auto auto auto;
  gap: 10px;
  align-items: center;
  margin-bottom: 16px;
}

.search-field {
  min-height: 40px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 13px;
  border: 1px solid #d8e0dc;
  border-radius: 8px;
  color: var(--muted);
  background: #fff;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.search-field:focus-within {
  border-color: #83a695;
  box-shadow: 0 0 0 3px rgba(47, 111, 86, 0.1);
}

.search-field input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  color: var(--ink);
  background: transparent;
  font: inherit;
}

.text-button.muted {
  color: var(--muted);
}

/* ---- 台账面板 ---- */
.ledger-panel {
  position: relative;
  overflow: hidden;
  border: 1px solid #dfe6e2;
  border-radius: 10px;
  background: #fff;
}

.ledger-loading {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  z-index: 2;
  background: #e8f0ec;
}

.ledger-loading span {
  display: block;
  height: 100%;
  width: 40%;
  border-radius: 2px;
  background: var(--brand);
  animation: loading-slide 1.1s ease-in-out infinite;
}

@keyframes loading-slide {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(350%); }
}

.ledger-head {
  display: grid;
  grid-template-columns: 56px minmax(260px, 1fr) 108px 168px 92px minmax(170px, auto);
  gap: 16px;
  align-items: center;
  min-height: 42px;
  padding: 0 20px;
  border-bottom: 1px solid var(--line);
  color: #65726b;
  background: #f7faf8;
  font-size: 11px;
  font-weight: 760;
  letter-spacing: 0.08em;
}

.col-index,
.col-date,
.col-status,
.col-stats {
  text-align: left;
}

/* ---- 台账行 ---- */
.ledger-row {
  position: relative;
  display: grid;
  grid-template-columns: 56px minmax(260px, 1fr) 108px 168px 92px minmax(170px, auto);
  gap: 16px;
  align-items: center;
  min-height: 84px;
  padding: 16px 20px 16px 24px;
  border-bottom: 1px solid var(--line);
  cursor: pointer;
  transition: background 0.16s ease;
  animation: row-in 0.4s ease both;
  animation-delay: calc(var(--row-i) * 45ms);
}

.ledger-row:last-of-type {
  border-bottom: 0;
}

.ledger-row:hover,
.ledger-row:focus-visible {
  background: #f4f9f6;
  outline: none;
}

.ledger-row::before {
  content: "";
  position: absolute;
  top: 14px;
  bottom: 14px;
  left: 0;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--brand);
  transform: scaleY(0);
  transition: transform 0.18s ease;
}

.ledger-row:hover::before,
.ledger-row:focus-visible::before {
  transform: scaleY(1);
}

@keyframes row-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .ledger-row {
    animation: none;
  }
}

/* 编号 */
.row-index {
  color: #9aa69f;
  font-family: var(--mono);
  font-size: 15px;
  transition: color 0.16s ease;
}

.ledger-row:hover .row-index {
  color: var(--brand);
}

/* 任务主体 */
.row-main {
  min-width: 0;
}

.row-title {
  margin: 0;
  overflow: hidden;
  color: var(--ink);
  font-family: var(--serif-display);
  font-size: 16.5px;
  font-weight: 700;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-sub {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 7px;
  min-width: 0;
}

.row-chips {
  display: inline-flex;
  flex-shrink: 0;
  gap: 5px;
}

.row-chips em {
  padding: 1px 7px;
  border: 1px solid #dbe5df;
  border-radius: 999px;
  color: #4d6157;
  background: #f4f8f6;
  font-size: 11px;
  font-style: normal;
}

.row-chips em.more {
  border-style: dashed;
  color: var(--muted);
}

.row-prompt {
  overflow: hidden;
  color: var(--muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 状态印章 */
.status-stamp {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  color: #44564e;
  background: #edf1ef;
  font-size: 12px;
  font-weight: 700;
  justify-self: start;
}

.stamp-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #81908a;
}

.status-stamp.done {
  color: #246044;
  background: #e3f0e9;
}

.status-stamp.done .stamp-dot {
  background: #2f7d57;
}

.status-stamp.running {
  color: #335f79;
  background: #e4eef5;
}

.status-stamp.running .stamp-dot {
  background: #3b6f8f;
  animation: dot-pulse 1.4s ease-in-out infinite;
}

.status-stamp.waiting {
  color: #8a571c;
  background: #f7ead8;
}

.status-stamp.waiting .stamp-dot {
  background: #b7791f;
}

.status-stamp.failed {
  color: #8f2f2f;
  background: #f8e3e1;
}

.status-stamp.failed .stamp-dot {
  background: #b4493d;
}

.status-stamp.canceled {
  color: #6a5d50;
  background: #eee8df;
}

@keyframes dot-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

@media (prefers-reduced-motion: reduce) {
  .status-stamp.running .stamp-dot {
    animation: none;
  }
}

/* 指标列 */
.row-stats {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.stat-pair {
  display: flex;
  gap: 14px;
  color: var(--muted);
  font-size: 12px;
}

.stat-pair strong {
  color: var(--ink-soft);
  font-family: var(--mono);
  font-size: 13px;
}

.coverage-track {
  position: relative;
  height: 5px;
  overflow: hidden;
  border-radius: 999px;
  background: #e8efeb;
}

.coverage-track i {
  position: absolute;
  inset: 0 auto 0 0;
  display: block;
  border-radius: inherit;
  background: var(--brand);
  transition: width 0.3s ease;
}

.coverage-note {
  color: var(--brand-ink);
  font-family: var(--mono);
  font-size: 11px;
  font-style: normal;
}

.coverage-note.muted {
  color: #9aa69f;
}

/* 日期 */
.row-date {
  color: var(--muted);
  font-family: var(--mono);
  font-size: 12px;
}

/* 操作列 */
.row-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 7px;
}

/* ---- 响应式 ---- */
@media (max-width: 1180px) {
  .library-toolbar {
    grid-template-columns: 1fr auto;
  }

  .ledger-head {
    display: none;
  }

  .ledger-row {
    grid-template-columns: 44px minmax(0, 1fr) auto;
    grid-template-areas:
      "index main status"
      "index stats stats"
      "index actions actions";
    row-gap: 10px;
  }

  .row-index {
    grid-area: index;
  }

  .row-main {
    grid-area: main;
  }

  .status-stamp {
    grid-area: status;
  }

  .row-stats {
    grid-area: stats;
  }

  .row-date {
    display: none;
  }

  .row-actions {
    grid-area: actions;
    justify-content: flex-start;
  }
}

@media (max-width: 820px) {
  .library-topbar {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .library-toolbar {
    grid-template-columns: 1fr;
  }

  .ledger-row {
    grid-template-columns: 1fr;
    grid-template-areas:
      "main"
      "status"
      "stats"
      "actions";
    padding-left: 20px;
  }

  .row-index {
    display: none;
  }

  .ledger-row::before {
    top: 10px;
    bottom: 10px;
  }

  .row-title {
    white-space: normal;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }
}
</style>
