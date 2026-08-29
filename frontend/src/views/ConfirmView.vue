<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, ChevronDown, Plus, RefreshCcw, X } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { useTasksStore } from '@/stores/tasks'
import { isUnauthorizedError } from '@/lib/authSession'
import { clarifyResearchPlan } from '@/api'
import type { ClarificationQuestionOut, ResearchPlanSuggestionOut } from '@/api/types'
import { buildClarificationPlan, mergeSourcePreferences, type ClarificationQuestion, type ResearchWeight } from '@/lib/clarifier'

const router = useRouter()
const authStore = useAuthStore()
const tasksStore = useTasksStore()

const taskTitle = ref('')
const prompt = ref('')
const researchMode = ref<string>('auto')
const reportDepth = ref('standard')
const timeRange = ref('recent_3_months')
const outputFormat = ref('markdown')
const competitors = ref<string[]>([])
const dimensions = ref<string[]>([])
const sources = ref<string[]>([])
const newCompetitor = ref('')
const newDimension = ref('')
const newSourcePreference = ref('')
const manualSourceInput = ref('')
const clarificationQuestions = ref<ClarificationQuestion[]>([])
const researchWeights = ref<ResearchWeight[]>([])
const planSuggestion = ref<ResearchPlanSuggestionOut | null>(null)
const planLoading = ref(false)
const planError = ref('')
const showAdvanced = ref(false)
const editPrompt = ref(false)

const canStart = computed(() => prompt.value.trim().length >= 8)
const isLoading = computed(() => tasksStore.isLoading)

const researchModeOptions = [
  { value: 'auto', label: '自动模式' },
  { value: 'competitive_research', label: '竞品研究' },
  { value: 'deep_research', label: '深度研究' },
]

const reportDepthOptions = [
  { value: 'brief', label: '简报' },
  { value: 'standard', label: '标准' },
  { value: 'detailed', label: '详细' },
]

const timeRangeOptions = [
  { value: 'recent_1_month', label: '近1个月' },
  { value: 'recent_3_months', label: '近3个月' },
  { value: 'recent_6_months', label: '近6个月' },
  { value: 'recent_1_year', label: '近1年' },
]

const outputFormatOptions = [
  { value: 'markdown', label: 'Markdown' },
  { value: 'pdf', label: 'PDF' },
  { value: 'docx', label: 'Word' },
]

const manualSourceUrls = computed(() => {
  return manualSourceInput.value.split(/[\s,]+/).filter(url => url.trim())
})

const budgetHint = ref({
  maxSearchRounds: 3,
  maxSources: 9,
  expectedMinutes: '2-4',
})

const displayedBudgetHint = computed(() => budgetHint.value)

function removeItem(list: string[], item: string) {
  const index = list.indexOf(item)
  if (index > -1) list.splice(index, 1)
}

function addCompetitor() {
  if (newCompetitor.value.trim()) {
    competitors.value.push(newCompetitor.value.trim())
    newCompetitor.value = ''
  }
}

function addDimension() {
  if (newDimension.value.trim()) {
    dimensions.value.push(newDimension.value.trim())
    newDimension.value = ''
  }
}

function addSourcePreference() {
  if (newSourcePreference.value.trim()) {
    sources.value.push(newSourcePreference.value.trim())
    newSourcePreference.value = ''
  }
}

function updateWeight(key: string, event: Event) {
  const target = event.target as HTMLInputElement
  const weight = researchWeights.value.find(w => w.key === key)
  if (weight) weight.value = Number(target.value)
}

function applyClarificationPlan() {
  const plan = buildClarificationPlan(prompt.value)
  const previousAnswers = new Map(clarificationQuestions.value.map((item) => [item.key, item.answer]))
  clarificationQuestions.value = plan.questions.map((item) => ({ ...item, answer: previousAnswers.get(item.key) ?? item.answer }))
  researchWeights.value = plan.weights
  budgetHint.value = plan.budgetHint
}

function mapPlanQuestion(item: ClarificationQuestionOut, previousAnswer = ''): ClarificationQuestion {
  return {
    key: item.key,
    label: item.label,
    question: item.question,
    answer: previousAnswer,
    reason: item.reason,
    answerType: item.answer_type,
    options: item.options,
    required: item.required,
  }
}

function isOptionSelected(item: ClarificationQuestion, option: string) {
  if (item.answerType === 'multi_choice') {
    return item.answer.split('、').map((value) => value.trim()).includes(option)
  }
  return item.answer.trim() === option
}

function chooseQuestionOption(item: ClarificationQuestion, option: string) {
  if (item.answerType !== 'multi_choice') {
    item.answer = option
    return
  }
  const selected = item.answer.split('、').map((value) => value.trim()).filter(Boolean)
  item.answer = selected.includes(option)
    ? selected.filter((value) => value !== option).join('、')
    : [...selected, option].join('、')
}

async function loadClarificationPlan() {
  if (!prompt.value.trim()) return
  planLoading.value = true
  planError.value = ''
  try {
    const plan = await clarifyResearchPlan(prompt.value.trim())
    const previousAnswers = new Map(clarificationQuestions.value.map((item) => [item.key, item.answer]))
    planSuggestion.value = plan
    clarificationQuestions.value = plan.questions.map((item) => mapPlanQuestion(item, previousAnswers.get(item.key) || ''))
    competitors.value = plan.competitors
    dimensions.value = plan.dimensions
    sources.value = plan.source_preferences
    researchMode.value = plan.research_type
    reportDepth.value = plan.report_depth
    timeRange.value = plan.time_range
    outputFormat.value = plan.output_format
    budgetHint.value = {
      maxSearchRounds: plan.research_type === 'deep_research' ? 4 : 3,
      maxSources: plan.research_type === 'deep_research' ? 15 : 10,
      expectedMinutes: plan.research_type === 'deep_research' ? '4-8' : '2-5',
    }
  } catch (error) {
    planError.value = error instanceof Error ? error.message : 'Agent 规划暂时不可用，已使用本地规则继续。'
    applyClarificationPlan()
  } finally {
    planLoading.value = false
  }
}

async function startResearch() {
  if (!canStart.value || isLoading.value) return
  editPrompt.value = false
  try {
    const task = await tasksStore.startResearchTask({
      prompt: prompt.value,
      title: taskTitle.value,
      competitors: competitors.value,
      dimensions: dimensions.value,
      sourcePreferences: mergeSourcePreferences(sources.value, manualSourceInput.value),
      clarificationAnswers: clarificationQuestions.value
        .filter((item) => item.answer.trim())
        .map((item) => ({ key: item.key, label: item.label, question: item.question, answer: item.answer.trim() })),
      assumptions: planSuggestion.value?.assumptions || [],
      researchWeights: researchWeights.value,
      researchMode: researchMode.value as 'auto' | 'competitive_research' | 'deep_research',
      reportDepth: reportDepth.value,
      timeRange: timeRange.value,
      outputFormat: outputFormat.value,
    })
    router.push({ path: '/run', query: { taskId: task.id } })
  } catch (error) {
    if (isUnauthorizedError(error)) {
      authStore.requireLogin('登录已过期，请重新登录后再开始研究。')
      return
    }
    authStore.errorMessage = error instanceof Error ? `研究启动失败：${error.message}` : '研究启动失败，请稍后重试。'
  }
}

function savePromptEdit() {
  editPrompt.value = false
  void loadClarificationPlan()
}

onMounted(() => {
  const draftPrompt = tasksStore.draftPrompt.trim()
  if (draftPrompt) {
    prompt.value = draftPrompt
  } else {
    router.replace('/workspace')
    return
  }
  void loadClarificationPlan()
})
</script>

<template>
  <section class="content-page">
    <header class="page-topbar">
      <div>
        <span class="eyebrow">Research plan</span>
        <h1>在开始前，请确认几个关键点</h1>
        <small class="page-subtitle">这能帮助专家团队更精准地锁定调研范围</small>
      </div>
      <div class="topbar-buttons">
        <button class="secondary-button" type="button" @click="router.push('/workspace')">返回</button>
        <button class="primary-button" type="button" :disabled="!canStart || isLoading" @click="startResearch">
          {{ isLoading ? '研究启动中' : '开始研究' }} <ArrowRight :size="17" />
        </button>
      </div>
    </header>

    <div class="clarify-flow">
      <!-- 需求确认卡 -->
      <section class="flow-card">
        <span class="flow-label">你的需求</span>
        <template v-if="!editPrompt">
          <p class="prompt-text">{{ prompt }}</p>
          <div class="prompt-actions">
            <button class="text-button" type="button" @click="editPrompt = true">修改需求</button>
            <button class="text-button" type="button" :disabled="planLoading" @click="loadClarificationPlan">
              <RefreshCcw :size="14" /> {{ planLoading ? '分析中' : '重新分析' }}
            </button>
          </div>
        </template>
        <template v-else>
          <textarea v-model="prompt" />
          <div class="prompt-edit-actions">
            <button class="primary-button compact" type="button" :disabled="planLoading" @click="savePromptEdit">
              <RefreshCcw :size="14" /> 保存并重新分析
            </button>
            <button class="secondary-button compact" type="button" @click="editPrompt = false">取消</button>
          </div>
        </template>
      </section>

      <!-- Agent 分析中 -->
      <section v-if="planLoading" class="flow-card loading-card">
        <RefreshCcw class="spin" :size="16" /> Agent 正在分析你的需求，生成定制追问…
      </section>

      <p v-if="planError" class="plan-fallback-note">{{ planError }}</p>
      <div v-if="planSuggestion?.warnings.length" class="plan-warning-list">
        <p v-for="warning in planSuggestion.warnings" :key="warning">{{ warning }}</p>
      </div>

      <!-- Agent 追问卡片 -->
      <section v-for="item in clarificationQuestions" :key="item.key" class="flow-card question-card">
        <strong>{{ item.question }}</strong>
        <small v-if="item.reason" class="question-reason">{{ item.reason }}</small>
        <div v-if="item.options?.length" class="question-options">
          <button
            v-for="option in item.options"
            :key="option"
            class="chip"
            :class="{ selected: isOptionSelected(item, option) }"
            type="button"
            @click="chooseQuestionOption(item, option)"
          >
            {{ option }}
          </button>
        </div>
        <textarea v-if="!item.options?.length" v-model="item.answer" placeholder="选填，可补充背景信息" />
      </section>

      <!-- 预算摘要 -->
      <p class="budget-summary">
        预计 {{ displayedBudgetHint.maxSearchRounds }} 轮搜索 · {{ displayedBudgetHint.maxSources }} 个候选来源 · 约 {{ displayedBudgetHint.expectedMinutes }} 分钟
      </p>

      <!-- 高级设置（默认折叠） -->
      <section class="flow-card advanced-card">
        <button class="advanced-toggle" type="button" @click="showAdvanced = !showAdvanced">
          <ChevronDown :size="16" class="chevron" :class="{ open: showAdvanced }" />
          高级设置（{{ competitors.length }} 个竞品 · {{ dimensions.length }} 个维度 · {{ sources.length }} 项来源偏好）
        </button>
        <div v-if="showAdvanced" class="advanced-body">
          <label class="field-block">
            <span>任务标题</span>
            <input v-model="taskTitle" class="text-input" placeholder="留空时自动使用研究需求前缀" />
          </label>

          <div class="field-block">
            <span>研究模式</span>
            <div class="segmented-control">
              <button
                v-for="item in researchModeOptions"
                :key="item.value"
                type="button"
                :class="{ selected: researchMode === item.value }"
                @click="researchMode = item.value"
              >
                {{ item.label }}
              </button>
            </div>
          </div>

          <div class="structured-settings-grid">
            <label class="field-block compact-field">
              <span>报告深度</span>
              <select v-model="reportDepth" class="select-input">
                <option v-for="item in reportDepthOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label class="field-block compact-field">
              <span>时间范围</span>
              <select v-model="timeRange" class="select-input">
                <option v-for="item in timeRangeOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
            <label class="field-block compact-field">
              <span>输出目标</span>
              <select v-model="outputFormat" class="select-input">
                <option v-for="item in outputFormatOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
              </select>
            </label>
          </div>

          <div class="field-block">
            <span>竞品对象</span>
            <div class="chip-row">
              <button v-for="item in competitors" :key="item" class="chip selected removable" type="button" @click="removeItem(competitors, item)">
                {{ item }} <X :size="13" />
              </button>
            </div>
            <form class="inline-add-form" @submit.prevent="addCompetitor">
              <input v-model="newCompetitor" class="text-input" placeholder="添加竞品名称" />
              <button class="secondary-button compact" type="submit"><Plus :size="14" /> 添加</button>
            </form>
          </div>

          <div class="field-block">
            <span>分析维度</span>
            <div class="chip-row">
              <button v-for="item in dimensions" :key="item" class="chip selected removable" type="button" @click="removeItem(dimensions, item)">
                {{ item }} <X :size="13" />
              </button>
            </div>
            <form class="inline-add-form" @submit.prevent="addDimension">
              <input v-model="newDimension" class="text-input" placeholder="添加分析维度" />
              <button class="secondary-button compact" type="submit"><Plus :size="14" /> 添加</button>
            </form>
          </div>

          <div class="field-block">
            <span>信息源策略</span>
            <div class="chip-row">
              <button v-for="item in sources" :key="item" class="chip selected removable" type="button" @click="removeItem(sources, item)">
                {{ item }} <X :size="13" />
              </button>
            </div>
            <form class="inline-add-form" @submit.prevent="addSourcePreference">
              <input v-model="newSourcePreference" class="text-input" placeholder="添加来源偏好" />
              <button class="secondary-button compact" type="submit"><Plus :size="14" /> 添加</button>
            </form>
          </div>

          <label class="field-block manual-url-field">
            <span>手动来源 URL</span>
            <textarea v-model="manualSourceInput" placeholder="每行一个 URL，也可以用空格或逗号分隔。没有搜索 API Key 时可直接粘贴官网、文档、定价页。" />
          </label>
          <div v-if="manualSourceUrls.length" class="manual-url-list">
            <span v-for="url in manualSourceUrls" :key="url">{{ url }}</span>
          </div>

          <div class="weight-list">
            <label v-for="item in researchWeights" :key="item.key" class="weight-row">
              <span>{{ item.label }}</span>
              <input type="range" min="5" max="45" step="5" :value="item.value" @input="updateWeight(item.key, $event)" />
              <strong>{{ item.value }}%</strong>
            </label>
          </div>
        </div>
      </section>

      <button class="primary-button start-button" type="button" :disabled="!canStart || isLoading" @click="startResearch">
        {{ isLoading ? '研究启动中' : '开始调研' }} <ArrowRight :size="17" />
      </button>
    </div>
  </section>
</template>

<style scoped>
.page-subtitle {
  display: block;
  margin-top: 4px;
  color: #7a8780;
  font-size: 13px;
  font-weight: 400;
}

.clarify-flow {
  display: grid;
  gap: 14px;
  max-width: 780px;
  margin: 0 auto;
}

.flow-card {
  display: grid;
  gap: 10px;
  padding: 20px;
  border: 1px solid #e0e7e3;
  border-radius: 12px;
  background: #fff;
}

.flow-label {
  color: #7a8780;
  font-size: 12px;
  font-weight: 700;
}

.prompt-text {
  margin: 0;
  color: #26342d;
  font-size: 15px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.prompt-actions {
  display: flex;
  gap: 16px;
}

.prompt-edit-actions {
  display: flex;
  gap: 10px;
}

.flow-card textarea {
  width: 100%;
  min-height: 92px;
  padding: 12px;
  border: 1px solid #dfe6e2;
  border-radius: 8px;
  outline: 0;
  resize: vertical;
  color: #24342d;
  background: #fbfcfb;
  line-height: 1.65;
}

.flow-card textarea:focus {
  border-color: #83a695;
  box-shadow: 0 0 0 3px rgba(47, 111, 86, 0.1);
}

.loading-card {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #4e5f56;
  font-size: 13px;
}

.spin {
  animation: spin 1.2s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.plan-fallback-note,
.plan-warning-list p {
  margin: 0;
  padding: 8px 10px;
  border-radius: 7px;
  color: #7b5522;
  background: #fff7e8;
  font-size: 12px;
  line-height: 1.45;
}

.plan-warning-list {
  display: grid;
  gap: 6px;
}

.question-card strong {
  color: #2e3b35;
  font-size: 15px;
  line-height: 1.5;
}

.question-reason {
  color: #7a8780;
  font-size: 12px;
  line-height: 1.45;
}

.question-options {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.question-options .chip {
  padding: 7px 13px;
  font-size: 13px;
}

.budget-summary {
  margin: 0;
  color: #76837c;
  font-size: 12px;
  text-align: center;
}

.advanced-card {
  gap: 0;
}

.advanced-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0;
  border: 0;
  background: none;
  color: #41544b;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}

.advanced-toggle .chevron {
  transition: transform 0.15s ease;
}

.advanced-toggle .chevron.open {
  transform: rotate(180deg);
}

.advanced-body {
  display: grid;
  gap: 14px;
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #e6ece9;
}

.field-block {
  display: block;
}

.field-block > span {
  display: block;
  margin-bottom: 8px;
  color: #59675f;
  font-size: 13px;
  font-weight: 720;
}

.field-block textarea {
  min-height: 92px;
}

.structured-settings-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.compact-field {
  margin-bottom: 0;
}

.manual-url-field textarea {
  min-height: 110px;
}

.chip-row {
  flex-wrap: wrap;
  gap: 8px;
}

.inline-add-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  margin-top: 10px;
}

.manual-url-list {
  display: grid;
  gap: 6px;
}

.manual-url-list span {
  min-width: 0;
  padding: 7px 9px;
  border-radius: 6px;
  color: #41544b;
  background: #f4f7f6;
  font-size: 12px;
  overflow-wrap: anywhere;
}

.weight-list {
  display: grid;
  gap: 10px;
}

.weight-row {
  display: grid;
  grid-template-columns: minmax(100px, 0.9fr) minmax(120px, 1fr) 46px;
  gap: 12px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid #e2e9e5;
  border-radius: 8px;
  background: #fbfcfb;
}

.weight-row span {
  color: #4e5f56;
  font-size: 13px;
}

.weight-row strong {
  color: #255641;
  font-size: 13px;
  text-align: right;
}

.weight-row input {
  width: 100%;
  accent-color: #2f7d57;
}

.start-button {
  justify-content: center;
  padding: 13px 20px;
  font-size: 15px;
}

@media (max-width: 640px) {
  .structured-settings-grid {
    grid-template-columns: 1fr;
  }
}
</style>
