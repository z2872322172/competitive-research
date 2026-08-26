<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  BellRing,
  BookOpen,
  Bot,
  Check,
  ChevronDown,
  ClipboardCheck,
  Database,
  Download,
  ExternalLink,
  Eye,
  FileText,
  FolderOpen,
  Gauge,
  Globe2,
  Layers3,
  Library,
  Link2,
  ListChecks,
  Pause,
  Plus,
  RefreshCcw,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
  X,
} from 'lucide-vue-next'
import {
  apiLogin,
  apiRegister,
  apiWhoami,
  buildAuthSession,
  cancelResearchTask,
  confirmResearchTask,
  createResearchTask,
  exportReport,
  exportReportArtifact,
  getResearchTask,
  getSourceSnapshot,
  listCompetitors,
  listResearchEvents,
  listResearchTasks,
  regenerateReport,
  resetDemoData,
  resumeResearchTask,
  reviewClaim,
  rerunResearchTask,
  type ClaimOut,
  type CompetitorProfileOut,
  type ResearchEventOut,
  type ResearchTaskOut,
  type SourceSnapshotOut,
  type TaskDetailOut,
} from './api'
import {
  clearAuthSession,
  isUnauthorizedError,
  loadAuthSession,
  saveAuthSession,
  type AuthUser,
} from './auth.js'
import {
  buildClarificationPlan,
  mergeSourcePreferences,
  parseManualSourceUrls,
  type ClarificationQuestion,
  type ResearchWeight,
} from './researchClarifier.js'
import { buildEvidenceQuery, buildEvidenceTraceState, buildEvidenceViewModel, buildEvidenceWallItems, filterEvidenceViewModels, sourceTypeLabel, type EvidenceViewModel } from './researchEvidence.js'
import { buildCompetitorReuseItems, buildCompetitorRows } from './researchCompetitors.js'
import { addStructuredDraftItem, buildStructuredTaskPayload, canStartResearchDraft } from './researchTaskDraft.js'
import { buildClaimQualityJudgement, buildLowRiskReviewCandidates, buildReviewItems, resolveReviewReason, selectReviewItem } from './researchReview.js'
import { nextPageAfterReview, nextPageAfterTaskRefresh } from './researchNavigation.js'
import { buildPostReviewReportUpdateState, buildReportSectionEvidenceItems, buildReportVersionItems, selectNewestReportVersion } from './researchReports.js'
import { buildReportExportDescriptor, buildReportExportFilename, buildReportExportFormats } from './researchExport.js'
import {
  buildTaskListQuery,
  buildTaskRecoveryFeedback,
  buildTaskSummaries,
  buildTaskSummary,
  getRunHistory,
  type RunHistoryItem,
  type TaskSummary,
} from './researchTasks.js'
import { buildResearchSyncFeedback, shouldPollResearchTask } from './researchPolling.js'
import { buildAuditEvents, buildResearchTimeline, buildResearchWorkbenchSummary, formatDuration } from './researchTimeline.js'

type Page = 'workspace' | 'confirm' | 'run' | 'review' | 'report' | 'research' | 'competitors'
type ClaimStatus = '已验证' | '低置信度' | '存在冲突' | '未披露' | '待补证'
type TimelineStatus = 'started' | 'succeeded' | 'failed' | 'skipped' | 'retrying'

type NavItem = {
  page: Page
  label: string
  icon: typeof Gauge
  enabled: boolean
}

type ResearchTask = {
  id?: number
  title: string
  scope: string
  status: string
  statusTone?: string
  statusReason?: string
  statusDescription?: string
  evidenceCount: number
  claimCount: number
  coverage: number
  updatedAt: string
  rawStatus?: string
  canRetry?: boolean
  canResume?: boolean
  canCancel?: boolean
}

type Evidence = EvidenceViewModel

type Claim = {
  id: number
  title: string
  target: string
  dimension: string
  status: ClaimStatus
  confidence: '高' | '中' | '低' | '冲突'
  evidence: number[]
  detail: string
  includeInReport: boolean
  reviewDecision?: string | null
  reviewReason?: string | null
  reviewedAt?: string | null
  evidenceSummaries?: { id: number; label: string }[]
  confidencePercent?: number
  coveragePercent?: number
  statusLabel?: string
  confidenceLabel?: string
  riskLevel?: 'low' | 'medium' | 'high'
  confidenceText?: string
  coverageText?: string
  statusText?: string
  evidenceText?: string
  qualityFlags?: string[]
  qualityFlagLabels?: string[]
}

type AuditEvent = {
  type: string
  time: string
  text: string
  detail?: string
}

type TimelineItem = {
  key: string
  nodeName: string
  label: string
  description?: string
  status: TimelineStatus
  statusLabel: string
  startedAt: string
  updatedAt: string
  durationMs: number
  summary: string
  error: string
}

type ReviewItem = {
  claimId?: number
  title: string
  kind: '冲突' | '低置信度' | '未披露'
  summary: string
  sources: string[]
  recommendation: string
  processed?: boolean
  reviewDecision?: string | null
  reviewReason?: string | null
  reviewedAt?: string | null
  evidenceSummaries?: { id: number; label: string }[]
  confidencePercent?: number
  coveragePercent?: number
  statusLabel?: string
  confidenceLabel?: string
}

const currentPage = ref<Page>('workspace')
const selectedEvidence = ref<Evidence | null>(null)
const prompt = ref('调研 Trae、Cursor、GitHub Copilot、Windsurf 的竞争格局，重点关注产品定位、核心功能、技术能力、定价和用户口碑')
const researchMode = ref<'auto' | 'competitive_research' | 'deep_research'>('auto')
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
const draftTaskId = ref<number | null>(null)
const selectedReportVersion = ref<number | null>(null)
const clarificationQuestions = ref<ClarificationQuestion[]>([])
const researchWeights = ref<ResearchWeight[]>([])
const budgetHint = ref({ maxSearchRounds: 3, maxSources: 9, expectedMinutes: '2-4' })
const isLoading = ref(false)
const isExporting = ref(false)
const isRegeneratingReport = ref(false)
const isBackendConnected = ref(false)
const errorMessage = ref('')

// ---------------------------------------------------------------------------
// 登录态（后端 AUTH_MODE=strict 时需要登录；disabled 模式下自动跳过登录门）
// ---------------------------------------------------------------------------
const authUser = ref<AuthUser | null>(loadAuthSession()?.user ?? null)
const authRequired = ref(false)
const authFormMode = ref<'login' | 'register'>('login')
const authUsername = ref('')
const authPassword = ref('')
const authWorkspace = ref('')
const authError = ref('')
const authSubmitting = ref(false)

function requireLogin(message = '') {
  clearAuthSession()
  authUser.value = null
  authError.value = message
  authRequired.value = true
}

async function submitAuthForm() {
  if (authSubmitting.value) return
  authSubmitting.value = true
  authError.value = ''
  try {
    const response =
      authFormMode.value === 'register'
        ? await apiRegister(authUsername.value.trim(), authPassword.value, authWorkspace.value.trim() || undefined)
        : await apiLogin(authUsername.value.trim(), authPassword.value)
    const session = buildAuthSession(response)
    saveAuthSession(session)
    authUser.value = session.user
    authRequired.value = false
    authPassword.value = ''
    authWorkspace.value = ''
    void loadTasks()
    void loadCompetitors()
  } catch (error) {
    authError.value = error instanceof Error ? error.message : '登录失败，请稍后重试。'
  } finally {
    authSubmitting.value = false
  }
}

function logout() {
  requireLogin('已退出登录。')
}
const taskSearch = ref('')
const taskStatusFilter = ref('all')
const evidenceCompetitorFilter = ref('all')
const evidenceDimensionFilter = ref('all')
const evidenceSourceTypeFilter = ref('all')
let pollingTimer: number | undefined
let pollingRequestInFlight = false
const syncMessage = ref('')

const navItems: NavItem[] = [
  { page: 'workspace', label: '工作台', icon: Gauge, enabled: true },
  { page: 'research', label: '我的调研', icon: FolderOpen, enabled: true },
  { page: 'competitors', label: '竞品库', icon: Database, enabled: true },
  { page: 'workspace', label: '知识库', icon: Library, enabled: false },
  { page: 'workspace', label: '情报监控', icon: BellRing, enabled: false },
]

const fallbackRecentTasks: ResearchTask[] = [
  {
    title: 'Trae AI 编程工具竞争格局',
    scope: 'AI 编程工具 · 标准研究',
    status: '运行中',
    evidenceCount: 12,
    claimCount: 7,
    coverage: 46,
    updatedAt: '12 分钟前',
  },
  {
    title: '飞书、钉钉、企业微信 SWOT',
    scope: '协同办公 · Battle Card',
    status: '待审阅',
    evidenceCount: 28,
    claimCount: 18,
    coverage: 91,
    updatedAt: '今天 14:20',
  },
  {
    title: 'Notion、飞书、Obsidian 功能对标',
    scope: '知识管理 · 功能对比',
    status: '已完成',
    evidenceCount: 34,
    claimCount: 24,
    coverage: 94,
    updatedAt: '昨天 18:45',
  },
]

const examples = [
  {
    title: '新能源汽车竞争格局',
    icon: Bot,
    desc: '分析特斯拉、比亚迪、理想的产品与定位竞争',
    prompt: '分析特斯拉、比亚迪、理想在新能源汽车市场的竞争格局，重点关注产品定位、价格带、技术能力、渠道策略和用户口碑',
  },
  {
    title: '竞品 SWOT 分析',
    icon: ShieldCheck,
    desc: '为飞书、钉钉、企业微信生成结构化 SWOT 对比',
    prompt: '为飞书、钉钉、企业微信生成协同办公市场的 SWOT 对比，重点关注产品定位、客户群、生态能力和商业化路径',
  },
  {
    title: '功能对标基准',
    icon: Layers3,
    desc: '横向对比 Notion、飞书、Obsidian 的核心功能',
    prompt: '对比 Notion、飞书、Obsidian 的知识管理核心功能、AI 能力、协作能力和定价差异',
  },
  {
    title: '市场趋势报告',
    icon: BarChart3,
    desc: '梳理 2026 年 AI 笔记赛道的关键趋势',
    prompt: '生成 AI 搜索产品市场趋势报告，覆盖核心玩家、商业模式、技术趋势、用户需求和风险',
  },
]

const expertAvatars = ['林', '市', '产', '价', '技', '舆', '证', '审', '报', '竞', '策', '数']

const competitors = ref(['Trae', 'Cursor', 'GitHub Copilot', 'Windsurf'])
const dimensions = ref(['产品定位', '核心功能', '定价策略', '用户口碑', '技术能力', '近期动态'])
const sources = ref(['官方来源优先', '产品文档', '新闻媒体', '开发者资料', '用户社区'])
const manualSourceInput = ref('')
const taskTitle = ref('')
const newCompetitor = ref('')
const newDimension = ref('')
const newSourcePreference = ref('')
const reportDepth = ref('standard')
const timeRange = ref('last_12_months')
const outputFormat = ref('comprehensive_report')
const keywords = ref(['Trae pricing', 'Cursor privacy mode', 'GitHub Copilot Business', 'Windsurf Pro plan'])
const researchModeOptions: Array<{
  value: 'auto' | 'competitive_research' | 'deep_research'
  label: string
  icon: typeof Bot | typeof ShieldCheck | typeof Sparkles
}> = [
  { value: 'auto', label: '自动', icon: Bot },
  { value: 'competitive_research', label: '竞品研究', icon: ShieldCheck },
  { value: 'deep_research', label: '深度研究', icon: Sparkles },
]
const reportDepthOptions = [
  { value: 'brief', label: '简版' },
  { value: 'standard', label: '标准' },
  { value: 'deep', label: '深度' },
]
const timeRangeOptions = [
  { value: 'last_3_months', label: '近 3 个月' },
  { value: 'last_6_months', label: '近 6 个月' },
  { value: 'last_12_months', label: '近 12 个月' },
  { value: 'all_time', label: '不限时间' },
]
const outputFormatOptions = [
  { value: 'comprehensive_report', label: '综合报告' },
  { value: 'battlecard', label: 'Battle Card' },
  { value: 'comparison_matrix', label: '对比矩阵' },
  { value: 'risk_brief', label: '风险简报' },
]
const reportExportFormats = buildReportExportFormats()

const fallbackPipeline: TimelineItem[] = [
  { key: 'fallback-plan', nodeName: 'plan_research', label: '需求理解', status: 'succeeded', statusLabel: '已完成', startedAt: '', updatedAt: '', durationMs: 0, summary: '研究规划员已拆解维度和关键词。', error: '' },
  { key: 'fallback-discover', nodeName: 'discover_sources', label: '检索派遣', status: 'succeeded', statusLabel: '已完成', startedAt: '', updatedAt: '', durationMs: 0, summary: '优先检索官网、文档、新闻与社区。', error: '' },
  { key: 'fallback-evidence', nodeName: 'extract_evidence', label: '证据采集', status: 'started', statusLabel: '进行中', startedAt: '', updatedAt: '', durationMs: 0, summary: '正在沉淀可引用 Evidence。', error: '' },
  { key: 'fallback-verify', nodeName: 'verify_claims', label: '引用质检', status: 'retrying', statusLabel: '重试中', startedAt: '', updatedAt: '', durationMs: 0, summary: '检查低置信度、缺证据与冲突结论。', error: '' },
  { key: 'fallback-report', nodeName: 'generate_report', label: '报告撰写', status: 'skipped', statusLabel: '未开始', startedAt: '', updatedAt: '', durationMs: 0, summary: '等待 Claim 质检完成。', error: '' },
]

const fallbackAuditEvents: AuditEvent[] = [
  { type: '规划', time: '10:02', text: '已将任务拆为产品定位、核心功能、定价策略、技术生态、用户口碑和近期动态 6 个维度。' },
  { type: '派遣', time: '10:03', text: '官方信息研究员开始检索 Trae、Cursor、GitHub Copilot、Windsurf 的官网、文档和价格页。' },
  { type: '发现', time: '10:05', text: '发现 Cursor Pricing 页面，提取 Team、Business 套餐和隐私模式相关描述。' },
  { type: '证据', time: '10:06', text: '新增证据 S12：Cursor Pricing 页面提到 Business plan 包含 Privacy Mode 和集中管理。' },
  { type: '冲突', time: '10:08', text: 'Windsurf Pro 价格在官网与较早第三方文章中不一致，已加入证据审阅。' },
  { type: '缺口', time: '10:11', text: 'Trae 企业版价格未在公开页面披露，当前标记为未披露。' },
  { type: '质检', time: '10:14', text: '当前事实性结论引用覆盖率 91%，仍有 2 条低置信度结论需要处理。' },
]

const fallbackEvidences: Evidence[] = [
  {
    id: 12,
    sourceId: 12,
    sourceType: 'official',
    type: '官方',
    title: 'Cursor Pricing',
    domain: 'cursor.com/pricing',
    publisher: 'Cursor',
    publishedAt: '2026-06-18',
    retrievedAt: '2026-07-29 10:06',
    confidence: 88,
    excerpt: 'Business plan includes privacy mode, admin controls, centralized billing and team management.',
    claims: 3,
    sourceUrl: 'https://cursor.com/pricing',
    canonicalUrl: 'https://cursor.com/pricing',
    locatorText: 'section: Business plan · paragraph: privacy mode',
    extractionMethod: 'demo_seed',
    snapshotHint: '本地 HTML 快照待接入读取接口',
  },
  {
    id: 18,
    sourceId: 18,
    sourceType: 'docs',
    type: '文档',
    title: 'GitHub Copilot Business Docs',
    domain: 'docs.github.com',
    publisher: 'GitHub Docs',
    publishedAt: '2026-05-22',
    retrievedAt: '2026-07-29 10:09',
    confidence: 86,
    excerpt: 'Copilot Business provides organization-level policies, seat management and enterprise controls.',
    claims: 2,
    sourceUrl: 'https://docs.github.com',
    canonicalUrl: 'https://docs.github.com',
    locatorText: 'section: Copilot Business · paragraph: organization policies',
    extractionMethod: 'demo_seed',
    snapshotHint: '本地 HTML 快照待接入读取接口',
  },
  {
    id: 24,
    sourceId: 24,
    sourceType: 'community',
    type: '社区',
    title: 'Developers compare Trae and Cursor',
    domain: 'reddit.com/r/programming',
    publisher: 'Reddit',
    publishedAt: '2026-07-01',
    retrievedAt: '2026-07-29 10:12',
    confidence: 46,
    excerpt: 'Users mention faster onboarding in Cursor while noting Trae has localized workflows.',
    claims: 1,
    sourceUrl: 'https://reddit.com/r/programming',
    canonicalUrl: 'https://reddit.com/r/programming',
    locatorText: 'thread: developer comparison · comment sample',
    extractionMethod: 'demo_seed',
    snapshotHint: '社交舆情快照待接入',
  },
  {
    id: 31,
    sourceId: 31,
    sourceType: 'news',
    type: '新闻',
    title: 'AI coding assistants market update',
    domain: 'techcrunch.com',
    publisher: 'TechCrunch',
    publishedAt: '2026-06-30',
    retrievedAt: '2026-07-29 10:13',
    confidence: 62,
    excerpt: 'The market is shifting from single completion tools to agentic coding environments.',
    claims: 2,
    conflicts: true,
    sourceUrl: 'https://techcrunch.com',
    canonicalUrl: 'https://techcrunch.com',
    locatorText: 'article body · paragraph: market shift',
    extractionMethod: 'demo_seed',
    snapshotHint: '本地 HTML 快照待接入读取接口',
  },
]

const fallbackClaims: Claim[] = [
  {
    id: 1,
    title: 'Cursor 在企业协作和隐私控制上更成熟',
    target: 'Cursor',
    dimension: '技术能力',
    status: '已验证',
    confidence: '高',
    evidence: [12, 18],
    detail: '官方价格页和文档均提到隐私模式、组织级策略和集中管理能力。',
    includeInReport: true,
  },
  {
    id: 2,
    title: 'Trae 的企业版价格未公开披露',
    target: 'Trae',
    dimension: '定价策略',
    status: '未披露',
    confidence: '中',
    evidence: [31],
    detail: '公开官网、文档和新闻未检索到明确企业版价格，应在报告中标记为未披露。',
    includeInReport: true,
  },
  {
    id: 3,
    title: 'Windsurf Pro 套餐价格存在来源冲突',
    target: 'Windsurf',
    dimension: '定价策略',
    status: '存在冲突',
    confidence: '冲突',
    evidence: [12, 31],
    detail: '官网价格与较早第三方文章不一致，建议采用官网价格并标注旧来源已过期。',
    includeInReport: true,
  },
  {
    id: 4,
    title: 'GitHub Copilot 的企业管理能力依托 GitHub 组织体系',
    target: 'GitHub Copilot',
    dimension: '生态能力',
    status: '已验证',
    confidence: '高',
    evidence: [18],
    detail: '官方文档显示其策略、席位和组织管理能力均围绕 GitHub 企业账户展开。',
    includeInReport: true,
  },
]

const fallbackReviewItems: ReviewItem[] = [
  {
    title: 'Windsurf Pro 套餐价格不一致',
    kind: '冲突',
    summary: '官网显示 $15/month，第三方文章显示 $10/month，但第三方文章发布时间早于官网页面。',
    sources: ['官网：$15/month · 可信度 85%', '第三方文章：$10/month · 可信度 48%'],
    recommendation: '采用官网价格，第三方文章作为过期信息附注。',
  },
  {
    title: 'Trae 企业版价格未公开披露',
    kind: '未披露',
    summary: '当前检索到官网、产品文档和新闻报道，但没有找到可引用的企业版公开价格。',
    sources: ['官网未披露', '文档未披露', '新闻未披露'],
    recommendation: '以“未披露”写入报告，避免推测具体价格。',
  },
  {
    title: 'Trae 用户口碑样本偏少',
    kind: '低置信度',
    summary: '社区讨论样本集中在少量渠道，尚不足以形成强结论。',
    sources: ['Reddit 样本 1 条', '技术博客样本 1 条'],
    recommendation: '保留为趋势观察，不进入执行摘要。',
  },
]

const fallbackCompetitorRows = [
  { name: 'Trae', category: 'AI 原生 IDE', reports: 3, verified: 8, conflicts: 1, update: '企业版价格未披露' },
  { name: 'Cursor', category: 'AI 代码编辑器', reports: 5, verified: 16, conflicts: 0, update: 'Business 套餐隐私能力已验证' },
  { name: 'GitHub Copilot', category: '开发者生态 AI 助手', reports: 4, verified: 14, conflicts: 0, update: '组织策略文档已更新' },
  { name: 'Windsurf', category: 'Agentic IDE', reports: 2, verified: 7, conflicts: 2, update: 'Pro 定价存在冲突' },
]

const taskStatusFilters = [
  { value: 'all', label: '全部' },
  { value: 'running', label: '运行中' },
  { value: 'waiting_review', label: '待审阅' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'canceled', label: '已取消' },
  { value: 'draft', label: '草稿' },
]

function claimStatusLabel(status: string): ClaimStatus {
  const labels: Record<string, ClaimStatus> = {
    verified: '已验证',
    low_confidence: '低置信度',
    conflict: '存在冲突',
    undisclosed: '未披露',
    needs_evidence: '待补证',
  }
  return labels[status] ?? '待补证'
}

function confidenceLabel(confidence: string): Claim['confidence'] {
  const labels: Record<string, Claim['confidence']> = {
    high: '高',
    medium: '中',
    low: '低',
    conflict: '冲突',
  }
  return labels[confidence] ?? '中'
}

function formatTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function formatDate(value: string | null) {
  if (!value) return '未披露'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const researchModeLabel = computed(() => {
  const selected = researchModeOptions.find((item) => item.value === researchMode.value)
  return selected?.label || '自动'
})

function buildTaskPayload() {
  return buildStructuredTaskPayload({
    prompt: prompt.value,
    title: taskTitle.value,
    competitors: competitors.value,
    dimensions: dimensions.value,
    sourcePreferences: sourcePreferencesForPayload.value,
    clarificationQuestions: clarificationQuestions.value,
    researchWeights: researchWeights.value,
    researchMode: researchMode.value,
    reportDepth: reportDepth.value,
    timeRange: timeRange.value,
    outputFormat: outputFormat.value,
  })
}

const recentTasks = computed<ResearchTask[]>(() => {
  if (!apiTasks.value.length) return isBackendConnected.value ? [] : fallbackRecentTasks
  return (buildTaskSummaries(apiTasks.value, taskDetailsById.value) as TaskSummary[]).map((summary) => ({
    ...summary,
    updatedAt: formatDate(summary.updatedAt),
  }))
})

const evidences = computed<Evidence[]>(() => {
  if (!taskDetail.value) return fallbackEvidences
  return taskDetail.value.evidence.map((item) => buildEvidenceViewModel(item, taskDetail.value?.claims.filter((claim) => claim.evidence_ids.includes(item.id)).length ?? 0))
})

const claims = computed<Claim[]>(() => {
  if (!taskDetail.value) return fallbackClaims
  return taskDetail.value.claims.map((item: ClaimOut) => {
    const quality = buildClaimQualityJudgement(item, evidences.value)
    return {
      id: item.id,
      title: item.display_text,
      target: item.subject,
      dimension: item.dimension || item.claim_type,
      status: claimStatusLabel(item.status),
      confidence: confidenceLabel(item.confidence),
      evidence: item.evidence_ids,
      detail: item.display_text,
      includeInReport: item.include_in_report,
      reviewDecision: item.review_decision,
      reviewReason: item.review_reason,
      reviewedAt: item.reviewed_at,
      evidenceSummaries: quality.evidenceSummaries,
      confidencePercent: quality.confidencePercent,
      coveragePercent: quality.coveragePercent,
      statusLabel: quality.statusText,
      riskLevel: quality.riskLevel,
      confidenceText: quality.confidenceText,
      coverageText: quality.coverageText,
      statusText: quality.statusText,
      evidenceText: quality.evidenceText,
      qualityFlags: quality.flags,
      qualityFlagLabels: quality.flagLabels,
    }
  })
})

const activeEvidenceFilters = computed(() => ({
  competitor: evidenceCompetitorFilter.value,
  dimension: evidenceDimensionFilter.value,
  sourceType: evidenceSourceTypeFilter.value,
}))

const evidenceWallItems = computed<Evidence[]>(() =>
  buildEvidenceWallItems(evidences.value, taskDetail.value?.claims ?? claims.value) as Evidence[],
)

const visibleEvidences = computed<Evidence[]>(() => {
  return filterEvidenceViewModels(evidenceWallItems.value, activeEvidenceFilters.value)
})

const evidenceSourceTypeOptions = computed(() => {
  const values = new Set<string>()
  const sourceTypes = taskDetail.value?.sources.map((source) => source.source_type) ?? evidences.value.map((item) => item.sourceType)
  sourceTypes.filter(Boolean).forEach((value) => values.add(value))
  return [{ value: 'all', label: '全部来源' }, ...Array.from(values).map((value) => ({ value, label: sourceTypeLabel(value) }))]
})

const evidenceCompetitorOptions = computed(() => {
  const values = new Set<string>()
  taskDetail.value?.task.scope.competitors?.filter(Boolean).forEach((value) => values.add(value))
  taskDetail.value?.claims.map((claim) => claim.subject).filter(Boolean).forEach((value) => values.add(value))
  return [{ value: 'all', label: '全部竞品' }, ...Array.from(values).map((value) => ({ value, label: value }))]
})

const evidenceDimensionOptions = computed(() => {
  const values = new Set<string>()
  taskDetail.value?.task.scope.dimensions?.filter(Boolean).forEach((value) => values.add(value))
  taskDetail.value?.claims
    .flatMap((claim) => [claim.dimension, claim.claim_type])
    .filter(Boolean)
    .forEach((value) => values.add(value))
  if (!taskDetail.value) fallbackClaims.map((claim) => claim.dimension).filter(Boolean).forEach((value) => values.add(value))
  return [{ value: 'all', label: '全部维度' }, ...Array.from(values).map((value) => ({ value, label: value }))]
})

const auditEvents = computed<AuditEvent[]>(() => {
  if (taskDetail.value && !taskEvents.value.length) return []
  if (!taskEvents.value.length) return fallbackAuditEvents
  return buildAuditEvents(taskEvents.value).map((event) => ({
    type: event.type,
    time: formatTime(event.time),
    text: event.text,
    detail: event.detail,
  }))
})

const researchTimeline = computed<TimelineItem[]>(() => {
  if (!taskEvents.value.length && !taskDetail.value) return fallbackPipeline
  return buildResearchTimeline(taskEvents.value, taskDetail.value?.latest_run ?? null) as TimelineItem[]
})

const workbenchSummary = computed(() =>
  buildResearchWorkbenchSummary(
    taskEvents.value.length ? taskEvents.value : [],
    {
      evidenceCount: evidenceCount.value,
      claimCount: claimCount.value,
    },
    taskDetail.value?.latest_run ?? null,
  ),
)

const timelineStatusCards = computed(() => {
  const counts = workbenchSummary.value.statusCounts
  return [
    { label: '已完成', value: counts.succeeded + counts.skipped },
    { label: '进行中', value: counts.started + counts.retrying },
    { label: '失败', value: counts.failed },
    { label: '总节点', value: workbenchSummary.value.totalNodes },
  ]
})

const timelineStatusNote = computed(
  () => workbenchSummary.value.failureReason || `当前阶段：${workbenchSummary.value.currentStageLabel}`,
)

const reviewItems = computed<ReviewItem[]>(() => {
  if (!taskDetail.value) return fallbackReviewItems
  return buildReviewItems(taskDetail.value.claims, evidences.value) as ReviewItem[]
})
const activeReviewItem = computed(() => selectReviewItem(reviewItems.value, selectedReviewClaimId.value ?? undefined) ?? null)
const activeReviewClaim = computed(() =>
  claims.value.find((claim) => claim.id === activeReviewItem.value?.claimId) ?? claims.value[0] ?? null,
)

const lowRiskReviewCandidates = computed(() => {
  if (!taskDetail.value) return []
  return buildLowRiskReviewCandidates(taskDetail.value.claims)
})

const manualSourceUrls = computed(() => parseManualSourceUrls(manualSourceInput.value))
const sourcePreferencesForPayload = computed(() => mergeSourcePreferences(sources.value, manualSourceInput.value))
const displayedBudgetHint = computed(() => ({
  ...budgetHint.value,
  maxSources: Math.max(budgetHint.value.maxSources, manualSourceUrls.value.length),
}))
const reportVersions = computed(() => [...(taskDetail.value?.reports ?? [])].sort((a, b) => a.version - b.version))
const reportVersionItems = computed(() => buildReportVersionItems(reportVersions.value))
const postReviewReportUpdate = computed(() =>
  buildPostReviewReportUpdateState(taskDetail.value?.reports ?? [], selectedReportVersion.value),
)
const latestReport = computed(() => reportVersions.value.at(-1) ?? null)
const activeReport = computed(() => {
  if (!reportVersions.value.length) return null
  return reportVersions.value.find((report) => report.version === selectedReportVersion.value) ?? latestReport.value
})
const reportSections = computed(() => [...(activeReport.value?.sections ?? [])].sort((a, b) => a.order_no - b.order_no))
const currentTaskTitle = computed(() => taskDetail.value?.task.title ?? '调研 Trae 竞争格局')
const evidenceCount = computed(() => visibleEvidences.value.length)
const claimCount = computed(() => claims.value.length)
const citationCoverage = computed(() => Math.round((activeReport.value?.citation_coverage ?? (taskDetail.value ? 0 : 0.94)) * 100))
const selectedEvidenceDetail = computed(() => selectedEvidence.value ?? visibleEvidences.value[0] ?? fallbackEvidences[0])
const canStart = computed(() =>
  canStartResearchDraft({
    prompt: prompt.value,
    competitors: competitors.value,
    dimensions: dimensions.value,
  }),
)
const hasContinueResearchRequest = computed(() => taskDetail.value?.claims.some((claim) => claim.review_decision === 'continue_research') ?? false)
const isReviewCompleted = computed(() => taskDetail.value?.task.status === 'completed')
const activeTaskSummary = computed(() => (taskDetail.value ? (buildTaskSummary(taskDetail.value.task, taskDetail.value) as TaskSummary) : null))
const runHistory = computed<RunHistoryItem[]>(() => (taskDetail.value ? getRunHistory(taskDetail.value.runs, taskDetail.value.task.current_run_id || taskDetail.value.latest_run?.id || undefined) : []))
const taskRecoveryFeedback = computed(() => (taskDetail.value ? buildTaskRecoveryFeedback(taskDetail.value.task, taskDetail.value.latest_run) : null))
const competitorRows = computed(() => buildCompetitorRows(competitorProfiles.value, fallbackCompetitorRows))
const localCompetitorProfileReuse = computed(() =>
  competitorProfiles.value
    .filter((profile) => competitors.value.some((name) => name.toLowerCase() === profile.name.toLowerCase()))
    .map((profile) => ({
      profile_id: profile.id,
      name: profile.name,
      source_count: profile.source_count,
      source_urls: profile.source_urls,
    })),
)
const competitorReuseItems = computed(() => {
  const taskReuseItems = buildCompetitorReuseItems(taskDetail.value?.task.scope ?? {})
  if (taskReuseItems.length) return taskReuseItems
  return buildCompetitorReuseItems({ competitor_profile_reuse: localCompetitorProfileReuse.value })
})
const currentRun = computed(() => runHistory.value.find((run) => run.isCurrent) ?? runHistory.value[0] ?? null)
const canRetryCurrentTask = computed(() => Boolean(activeTaskSummary.value?.canRetry))
const canResumeCurrentTask = computed(() => Boolean(activeTaskSummary.value?.canResume))
const canCancelCurrentTask = computed(() => Boolean(activeTaskSummary.value?.canCancel))
const displayMessage = computed(() => errorMessage.value || syncMessage.value)

function go(page: Page) {
  currentPage.value = page
  if (page === 'report') selectedEvidence.value = visibleEvidences.value[0]
  if (page === 'competitors') void loadCompetitors()
}

function selectReportVersion(version: number) {
  selectedReportVersion.value = version
}

function viewLatestPostReviewReport() {
  if (!postReviewReportUpdate.value.latestVersion) return
  selectedReportVersion.value = postReviewReportUpdate.value.latestVersion
}

function triggerReportDownload(payload: BlobPart, filename: string, mimeType: string) {
  const blob = new Blob([payload], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function chooseExample(examplePrompt: string) {
  prompt.value = examplePrompt
}

function applyClarificationPlan() {
  const plan = buildClarificationPlan(prompt.value)
  clarificationQuestions.value = plan.questions
  researchWeights.value = plan.weights
  budgetHint.value = plan.budgetHint
  sources.value = plan.sourcePreferences
}

function updateWeight(key: string, value: Event) {
  const target = value.target as HTMLInputElement
  const weight = researchWeights.value.find((item) => item.key === key)
  if (weight) weight.value = Number(target.value)
}

function removeItem(list: string[], item: string) {
  const index = list.indexOf(item)
  if (index >= 0) list.splice(index, 1)
}

function selectReviewClaim(item: ReviewItem) {
  if (!item.claimId) return
  selectedReviewClaimId.value = item.claimId
}

function addCompetitor() {
  competitors.value = addStructuredDraftItem(competitors.value, newCompetitor.value)
  newCompetitor.value = ''
}

function addDimension() {
  dimensions.value = addStructuredDraftItem(dimensions.value, newDimension.value)
  newDimension.value = ''
}

function addSourcePreference() {
  sources.value = addStructuredDraftItem(sources.value, newSourcePreference.value)
  newSourcePreference.value = ''
}

function selectEvidence(evidenceId: number | string) {
  selectedEvidence.value = visibleEvidences.value.find((item) => item.id === evidenceId) ?? visibleEvidences.value[0]
}

function openEvidenceSource(evidence: Evidence) {
  const trace = evidenceTraceForEvidence(evidence)
  if (!trace.canOpenSource) return
  window.open(trace.sourceUrl, '_blank', 'noopener,noreferrer')
}

function reviewEvidenceSummaries(item: ReviewItem) {
  if (item.evidenceSummaries?.length) return item.evidenceSummaries
  return item.sources.map((source) => ({ id: '', label: source }))
}

function claimEvidenceSummaries(claim: Claim) {
  if (claim.evidenceSummaries?.length) return claim.evidenceSummaries
  return claim.evidence.map((id) => ({ id, label: id }))
}

function isSnapshotLoading(evidence: Evidence) {
  return evidenceTraceForEvidence(evidence).snapshotStatus === 'loading'
}

function evidenceTraceForEvidence(evidence: Evidence) {
  return buildEvidenceTraceState(evidence, sourceSnapshots.value[evidence.sourceId], {
    loading: snapshotLoadingBySourceId.value[evidence.sourceId],
    error: snapshotErrorsBySourceId.value[evidence.sourceId],
  })
}

function snapshotTextForEvidence(evidence: Evidence) {
  return evidenceTraceForEvidence(evidence).snapshotText
}

function snapshotButtonLabel(evidence: Evidence) {
  const status = evidenceTraceForEvidence(evidence).snapshotStatus
  if (status === 'loading') return '\u8bfb\u53d6\u4e2d'
  if (status === 'error') return '\u91cd\u65b0\u8bfb\u53d6'
  if (status === 'available') return '\u5237\u65b0\u6458\u8981'
  return '\u67e5\u770b\u6458\u8981'
}

async function loadEvidenceSnapshot(evidence: Evidence) {
  const trace = evidenceTraceForEvidence(evidence)
  if (!taskDetail.value || !trace.canLoadSnapshot) return
  snapshotLoadingBySourceId.value = { ...snapshotLoadingBySourceId.value, [evidence.sourceId]: true }
  snapshotErrorsBySourceId.value = { ...snapshotErrorsBySourceId.value, [evidence.sourceId]: '' }
  try {
    const snapshot = await getSourceSnapshot(evidence.sourceId)
    sourceSnapshots.value = { ...sourceSnapshots.value, [evidence.sourceId]: snapshot }
  } catch (error) {
    snapshotErrorsBySourceId.value = {
      ...snapshotErrorsBySourceId.value,
      [evidence.sourceId]: error instanceof Error ? error.message : 'unknown error',
    }
  } finally {
    snapshotLoadingBySourceId.value = { ...snapshotLoadingBySourceId.value, [evidence.sourceId]: false }
  }
}

function statusClass(status: ClaimStatus | ResearchTask['status'] | ReviewItem['kind']) {
  return status.replace(/\s/g, '-')
}

function timelineStatusClass(status: TimelineStatus) {
  return `node-${status}`
}

function shouldPollTask(detail = taskDetail.value) {
  return shouldPollResearchTask(detail)
}

function syncPollingState(detail = taskDetail.value) {
  if (shouldPollTask(detail) && detail?.task.id) {
    if (pollingTimer === undefined) startPolling(detail.task.id)
    return
  }
  stopPolling()
}

function applyResearchSyncFeedback(detail = taskDetail.value, error: unknown = null) {
  const feedback = buildResearchSyncFeedback({ detail, events: taskEvents.value, error })
  syncMessage.value = feedback?.message ?? ''
  return feedback
}

function stopPolling() {
  if (pollingTimer !== undefined) {
    window.clearInterval(pollingTimer)
    pollingTimer = undefined
  }
}

function resetEvidenceFilters() {
  evidenceCompetitorFilter.value = 'all'
  evidenceDimensionFilter.value = 'all'
  evidenceSourceTypeFilter.value = 'all'
}

function startPolling(taskId: number) {
  stopPolling()
  pollingTimer = window.setInterval(async () => {
    if (pollingRequestInFlight) return
    pollingRequestInFlight = true
    try {
      const detail = await loadTaskDetail(taskId)
      syncPollingState(detail)
    } catch (error) {
      applyResearchSyncFeedback(taskDetail.value, error)
    } finally {
      pollingRequestInFlight = false
    }
  }, 1500)
}

async function loadTasks() {
  try {
    const tasks = await listResearchTasks(buildTaskListQuery(taskSearch.value, taskStatusFilter.value))
    apiTasks.value = tasks
    const detailResults = await Promise.allSettled(tasks.map((task) => getResearchTask(task.id)))
    const nextDetailsById: Record<string, TaskDetailOut> = {}
    detailResults.forEach((result, index) => {
      if (result.status === 'fulfilled') nextDetailsById[tasks[index].id] = result.value
    })
    taskDetailsById.value = nextDetailsById
    isBackendConnected.value = true
    errorMessage.value = ''
  } catch (error) {
    if (isUnauthorizedError(error)) {
      // 后端处于强制鉴权模式：展示登录门，而不是退回本地演示数据。
      requireLogin(error instanceof Error && error.message ? '请先登录后查看研究数据。' : '')
      return
    }
    isBackendConnected.value = false
    errorMessage.value = '后端暂未连接，当前展示本地原型数据。'
  }
}

async function loadCompetitors() {
  try {
    competitorProfiles.value = await listCompetitors()
  } catch {
    competitorProfiles.value = []
  }
}

function applyTaskFilters() {
  void loadTasks()
}

function clearTaskFilters() {
  taskSearch.value = ''
  taskStatusFilter.value = 'all'
  void loadTasks()
}

async function loadTaskDetail(taskId: number): Promise<TaskDetailOut> {
  taskDetail.value = await getResearchTask(taskId, buildEvidenceQuery(activeEvidenceFilters.value))
  taskDetailsById.value = { ...taskDetailsById.value, [taskId]: taskDetail.value }
  taskEvents.value = await listResearchEvents(taskId)
  prompt.value = taskDetail.value.task.prompt
  selectedReportVersion.value = taskDetail.value.reports.at(-1)?.version ?? null
  selectedEvidence.value = visibleEvidences.value[0] ?? null
  selectedReviewClaimId.value = selectReviewItem(reviewItems.value, selectedReviewClaimId.value ?? undefined)?.claimId ?? null
  const nextPage = nextPageAfterTaskRefresh(taskDetail.value, currentPage.value)
  if (nextPage !== currentPage.value) currentPage.value = nextPage
  syncPollingState(taskDetail.value)
  applyResearchSyncFeedback(taskDetail.value)
  return taskDetail.value
}

async function openTask(task: ResearchTask) {
  if (!task.id) {
    go(task.status === '已完成' ? 'report' : 'run')
    return
  }

  try {
    isLoading.value = true
    resetEvidenceFilters()
    await loadTaskDetail(task.id)
    draftTaskId.value = task.rawStatus === 'draft' ? task.id : null
    if (task.rawStatus === 'draft') applyClarificationPlan()
    go(task.rawStatus === 'draft' ? 'confirm' : task.rawStatus === 'completed' ? 'report' : task.rawStatus === 'waiting_review' ? 'review' : 'run')
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '加载任务失败。'
  } finally {
    isLoading.value = false
  }
}

async function applyEvidenceFilters() {
  if (!taskDetail.value) {
    selectedEvidence.value = visibleEvidences.value[0] ?? null
    return
  }
  try {
    isLoading.value = true
    await loadTaskDetail(taskDetail.value.task.id)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '筛选证据失败。'
  } finally {
    isLoading.value = false
  }
}

function createDraftResearchTask() {
  if (!canStart.value || isLoading.value) return
  applyClarificationPlan()
  draftTaskId.value = null
  taskDetail.value = null
  taskEvents.value = []
  selectedEvidence.value = null
  selectedReviewClaimId.value = null
  resetEvidenceFilters()
  selectedReportVersion.value = null
  manualSourceInput.value = ''
  syncMessage.value = ''
  currentPage.value = 'confirm'
  stopPolling()
  errorMessage.value = ''
}

async function startResearch() {
  if (!canStart.value || isLoading.value) return
  try {
    isLoading.value = true
    if (!clarificationQuestions.value.length || !researchWeights.value.length) applyClarificationPlan()
    let taskId = taskDetail.value?.task.status === 'draft' ? taskDetail.value.task.id : draftTaskId.value
    if (!taskId) {
      const task = await createResearchTask(buildTaskPayload())
      taskId = task.id
      await loadTaskDetail(taskId)
    }
    await confirmResearchTask(taskId, true)
    await loadTasks()
    await loadCompetitors()
    await loadTaskDetail(taskId)
    draftTaskId.value = null
    currentPage.value = 'run'
    errorMessage.value = ''
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '启动研究失败，请确认后端服务已启动。'
  } finally {
    isLoading.value = false
  }
}

async function refreshCurrentTask() {
  if (!taskDetail.value) return
  try {
    isLoading.value = true
    await loadTaskDetail(taskDetail.value.task.id)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '刷新任务失败。'
  } finally {
    isLoading.value = false
  }
}

async function handleReview(item: ReviewItem, decision: 'accept' | 'mark_uncertain' | 'exclude' | 'continue_research') {
  if (!item.claimId) return
  try {
    isLoading.value = true
    await reviewClaim(item.claimId, decision, resolveReviewReason(item, reviewReasons.value[item.claimId]))
    reviewReasons.value = { ...reviewReasons.value, [item.claimId]: '' }
    const taskId = taskDetail.value?.task.id
    if (taskId) {
      await loadTaskDetail(taskId)
    }
    await loadTasks()
    const nextPage = nextPageAfterReview(taskDetail.value, decision)
    if (nextPage === 'report') {
      currentPage.value = 'report'
      errorMessage.value = 'Review complete. The refreshed report is ready.'
      return
    }
    if (nextPage === 'run') {
      currentPage.value = 'run'
      errorMessage.value = 'Continue-research request recorded. Start another research run when ready.'
      return
    }
    if (decision === 'continue_research') {
      if (taskId) {
        currentPage.value = 'run'
      }
      errorMessage.value = '已标记继续查证，任务保持待审阅，可再次发起研究。'
      return
    }
    errorMessage.value = '已提交审核决策。'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '提交审核失败。'
  } finally {
    isLoading.value = false
  }
}

async function handleBatchAcceptLowRiskClaims() {
  const candidates = [...lowRiskReviewCandidates.value]
  const taskId = taskDetail.value?.task.id
  if (!taskId || !candidates.length || isLoading.value) return

  try {
    isLoading.value = true
    for (const candidate of candidates) {
      await reviewClaim(candidate.claimId, 'accept', candidate.reason)
    }
    await loadTaskDetail(taskId)
    await loadTasks()
    if (nextPageAfterReview(taskDetail.value, 'accept') === 'report') {
      currentPage.value = 'report'
      errorMessage.value = `Batch accepted ${candidates.length} low-risk Claims. The refreshed report is ready.`
      return
    }
    errorMessage.value = `已批量接受 ${candidates.length} 条低风险 Claim。`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量接受低风险 Claim 失败。'
  } finally {
    isLoading.value = false
  }
}

async function continueResearch() {
  if (!taskDetail.value || isLoading.value) return
  try {
    isLoading.value = true
    const taskId = taskDetail.value.task.id
    await rerunResearchTask(taskId, true)
    await loadTasks()
    await loadTaskDetail(taskId)
    currentPage.value = 'run'
    errorMessage.value = '已重新发起研究。'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '重新发起研究失败。'
  } finally {
    isLoading.value = false
  }
}

async function retryTask(task?: ResearchTask) {
  const taskId = task?.id ?? taskDetail.value?.task.id
  if (!taskId || isLoading.value) return
  try {
    isLoading.value = true
    await rerunResearchTask(taskId, true)
    await loadTasks()
    await loadTaskDetail(taskId)
    currentPage.value = 'run'
    errorMessage.value = '已重新发起研究。'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '重试任务失败。'
  } finally {
    isLoading.value = false
  }
}

async function resumeTask(task?: ResearchTask) {
  const taskId = task?.id ?? taskDetail.value?.task.id
  if (!taskId || isLoading.value) return
  try {
    isLoading.value = true
    await resumeResearchTask(taskId, true)
    await loadTasks()
    await loadTaskDetail(taskId)
    currentPage.value = 'run'
    errorMessage.value = '已从失败节点继续执行。'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '继续执行失败。'
  } finally {
    isLoading.value = false
  }
}

async function cancelTask(task?: ResearchTask) {
  const taskId = task?.id ?? taskDetail.value?.task.id
  if (!taskId || isLoading.value) return
  try {
    isLoading.value = true
    await cancelResearchTask(taskId, '用户在任务列表中取消')
    stopPolling()
    await loadTasks()
    await loadTaskDetail(taskId)
    currentPage.value = 'research'
    errorMessage.value = '任务已取消。'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '取消任务失败。'
  } finally {
    isLoading.value = false
  }
}

async function resetLocalDemoData() {
  try {
    isLoading.value = true
    const result = await resetDemoData()
    taskDetail.value = null
    taskEvents.value = []
    selectedEvidence.value = null
    resetEvidenceFilters()
    selectedReportVersion.value = null
    manualSourceInput.value = ''
    syncMessage.value = ''
    await loadTasks()
    await loadCompetitors()
    errorMessage.value = `已重置 Demo 数据，删除 ${result.deleted_tasks} 个任务。`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '重置 Demo 数据失败。'
  } finally {
    isLoading.value = false
  }
}

async function exportCurrentReport(format = 'markdown') {
  if (!activeReport.value || isExporting.value) return
  try {
    isExporting.value = true
    const descriptor = buildReportExportDescriptor(format)
    const filename = buildReportExportFilename(currentTaskTitle.value || 'competitive-research-report', format)
    if (format === 'markdown') {
      const result = await exportReport(activeReport.value.id, 'markdown')
      triggerReportDownload(result.content, filename, descriptor.mimeType)
    } else {
      if (format !== 'pdf' && format !== 'docx') throw new Error('不支持的导出格式。')
      const blob = await exportReportArtifact(activeReport.value.id, format)
      triggerReportDownload(blob, filename, descriptor.mimeType)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出报告失败。'
  } finally {
    isExporting.value = false
  }
}

async function regenerateCurrentReport() {
  const taskId = taskDetail.value?.task.id
  if (!taskId || isRegeneratingReport.value) return
  try {
    isRegeneratingReport.value = true
    const report = await regenerateReport(taskId)
    await loadTaskDetail(taskId)
    await loadTasks()
    selectedReportVersion.value = report.version ?? selectNewestReportVersion(taskDetail.value?.reports ?? [])
    errorMessage.value = `已生成报告 v${selectedReportVersion.value}。`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '重新生成报告失败。'
  } finally {
    isRegeneratingReport.value = false
  }
}

onMounted(async () => {
  const session = loadAuthSession()
  if (session?.token) {
    try {
      // 校验本地令牌仍有效（过期/被禁用则清除并进入登录门）。
      const user = await apiWhoami()
      saveAuthSession({ token: session.token, user })
      authUser.value = user
    } catch (error) {
      if (isUnauthorizedError(error)) {
        requireLogin('登录已过期，请重新登录。')
        return
      }
    }
  }
  void loadTasks()
  void loadCompetitors()
})
onBeforeUnmount(stopPolling)
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <button class="brand-row" type="button" @click="go('workspace')">
        <span class="brand-mark"><Sparkles :size="18" /></span>
        <span>Verda</span>
      </button>

      <nav class="nav-list" aria-label="主导航">
        <button
          v-for="item in navItems"
          :key="item.label"
          class="nav-item"
          :class="{ active: currentPage === item.page && item.enabled, disabled: !item.enabled }"
          type="button"
          :disabled="!item.enabled"
          @click="go(item.page)"
        >
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </button>
      </nav>

      <section class="workspace-summary" aria-label="工作区摘要">
        <div>
          <BookOpen :size="17" />
          <strong>研究工作区</strong>
        </div>
        <dl>
          <dt>本月报告</dt>
          <dd>8</dd>
          <dt>证据沉淀</dt>
          <dd>221</dd>
          <dt>平均覆盖率</dt>
          <dd>92%</dd>
        </dl>
      </section>

      <section v-if="authUser" class="auth-user" aria-label="当前登录用户">
        <div class="auth-user-id">
          <ShieldCheck :size="15" />
          <span>{{ authUser.username }}</span>
        </div>
        <p class="auth-user-workspace">{{ authUser.workspaces[0]?.workspace_id ?? '-' }}</p>
        <button class="auth-logout" type="button" @click="logout">退出登录</button>
      </section>
    </aside>

    <main class="main-surface">
      <div v-if="authRequired" class="auth-gate">
        <form class="auth-panel" @submit.prevent="submitAuthForm">
          <h2>{{ authFormMode === 'login' ? '登录 Verda' : '注册新账号' }}</h2>
          <p class="auth-hint">
            {{ authFormMode === 'login' ? '输入账号密码进入你的研究工作区。' : '注册后自动创建个人工作区；填写共享工作区 ID 可加入团队。' }}
          </p>
          <label class="auth-field">
            <span>用户名</span>
            <input v-model="authUsername" type="text" autocomplete="username" required minlength="3" placeholder="username" />
          </label>
          <label class="auth-field">
            <span>密码</span>
            <input v-model="authPassword" type="password" autocomplete="current-password" required minlength="8" placeholder="至少 8 位" />
          </label>
          <label v-if="authFormMode === 'register'" class="auth-field">
            <span>共享工作区 ID（可选）</span>
            <input v-model="authWorkspace" type="text" placeholder="留空则创建个人工作区" />
          </label>
          <p v-if="authError" class="auth-error">{{ authError }}</p>
          <button class="auth-submit" type="submit" :disabled="authSubmitting">
            {{ authSubmitting ? '处理中…' : authFormMode === 'login' ? '登录' : '注册并登录' }}
          </button>
          <button
            class="auth-switch"
            type="button"
            @click="authFormMode = authFormMode === 'login' ? 'register' : 'login'; authError = ''"
          >
            {{ authFormMode === 'login' ? '没有账号？注册一个' : '已有账号？直接登录' }}
          </button>
        </form>
      </div>

      <p v-if="displayMessage && !authRequired" class="error-banner">{{ displayMessage }}</p>
      <section v-if="currentPage === 'workspace'" class="workspace-page home-page">
        <header class="home-topline">
          <button class="feature-pill" type="button">
            <Sparkles :size="15" />
            新功能上线
          </button>
        </header>

        <section class="home-hero" aria-label="竞品分析入口">
          <div class="home-heading">
            <h1>下午好，林研究员</h1>
            <p>你的 AI 竞品分析 Agent —— 48 位专家协作，无证据不立论</p>
          </div>

          <div class="chat-composer">
            <textarea
              v-model="prompt"
              aria-label="研究需求"
              placeholder="想分析哪个市场、公司或竞争策略？例如：分析 Notion / 飞书 / Obsidian 的产品与定价竞争格局"
            />
            <div class="chat-toolbar">
              <span>48 位专家 · 真实网页 · 无证据不立论</span>
              <div>
                <button class="model-button" type="button">
                  <Bot :size="15" />
                  切换模型
                  <ChevronDown :size="14" />
                </button>
                <button class="icon-button subtle" type="button" title="上传资料"><Upload :size="17" /></button>
                <button class="send-button" type="button" :disabled="!canStart || isLoading" title="创建研究计划" @click="createDraftResearchTask">
                  <ArrowRight :size="19" />
                </button>
              </div>
            </div>
          </div>

          <div class="prompt-label">试试这些示例</div>
          <div class="home-example-grid">
            <button v-for="example in examples" :key="example.title" class="home-example-card" type="button" @click="chooseExample(example.prompt)">
              <span class="example-icon"><component :is="example.icon" :size="20" /></span>
              <strong>{{ example.title }}</strong>
              <small>{{ example.desc }}</small>
            </button>
          </div>

          <div class="expert-strip" aria-label="专家协作概览">
            <span v-for="avatar in expertAvatars" :key="avatar">{{ avatar }}</span>
            <button type="button" @click="go('research')">查看全部 48 位 →</button>
          </div>
        </section>
      </section>

      <section v-else-if="currentPage === 'confirm'" class="content-page">
        <header class="page-topbar">
          <div>
            <span class="eyebrow">Research plan</span>
            <h1>确认研究计划</h1>
          </div>
          <div class="topbar-buttons">
            <button class="secondary-button" type="button" @click="go('workspace')">返回</button>
            <button class="primary-button" type="button" :disabled="!canStart || isLoading" @click="startResearch">
              {{ isLoading ? '研究启动中' : '开始研究' }} <ArrowRight :size="17" />
            </button>
          </div>
        </header>

        <div class="confirm-grid">
          <section class="form-panel">
            <label class="field-block">
              <span>任务标题</span>
              <input v-model="taskTitle" class="text-input" placeholder="留空时自动使用研究需求前缀" />
            </label>

            <label class="field-block">
              <span>原始需求</span>
              <textarea v-model="prompt" />
            </label>

            <div class="field-block">
              <span>研究模式</span>
              <div class="segmented-control research-mode-control">
                <button
                  v-for="item in researchModeOptions"
                  :key="item.value"
                  type="button"
                  :class="{ selected: researchMode === item.value }"
                  @click="researchMode = item.value"
                >
                  <component :is="item.icon" :size="14" />
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

            <div class="clarifier-block">
              <div class="section-header">
                <h2>Agent 追问</h2>
                <button class="text-button" type="button" @click="applyClarificationPlan"><RefreshCcw :size="15" /> 重新生成</button>
              </div>
              <div class="question-list">
                <label v-for="item in clarificationQuestions" :key="item.key" class="question-card">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.question }}</strong>
                  <textarea v-model="item.answer" />
                </label>
              </div>
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

            <label class="field-block manual-url-field">
              <span>手动来源 URL</span>
              <textarea v-model="manualSourceInput" placeholder="每行一个 URL，也可以用空格或逗号分隔。没有搜索 API Key 时可直接粘贴官网、文档、定价页。" />
            </label>

            <div class="weight-list">
              <label v-for="item in researchWeights" :key="item.key" class="weight-row">
                <span>{{ item.label }}</span>
                <input type="range" min="5" max="45" step="5" :value="item.value" @input="updateWeight(item.key, $event)" />
                <strong>{{ item.value }}%</strong>
              </label>
            </div>
          </section>

          <aside class="suggestion-panel">
            <div class="panel-heading">
              <Sparkles :size="18" />
              <h2>研究设置</h2>
            </div>
            <section>
              <h3>范围预览</h3>
              <dl class="scope-preview">
                <div>
                  <dt>竞品</dt>
                  <dd>{{ competitors.length }} 个</dd>
                </div>
                <div>
                  <dt>维度</dt>
                  <dd>{{ dimensions.length }} 个</dd>
                </div>
                <div>
                  <dt>手动 URL</dt>
                  <dd>{{ manualSourceUrls.length }} 个</dd>
                </div>
                <div>
                  <dt>模式</dt>
                  <dd>{{ researchModeLabel }}</dd>
                </div>
              </dl>
              <div v-if="manualSourceUrls.length" class="manual-url-list">
                <span v-for="url in manualSourceUrls" :key="url">{{ url }}</span>
              </div>
            </section>
            <section>
              <h3>信息源策略</h3>
              <div class="chip-row compact-chips">
                <button v-for="item in sources" :key="item" class="chip selected removable" type="button" @click="removeItem(sources, item)">
                  {{ item }} <X :size="13" />
                </button>
              </div>
              <form class="inline-add-form compact-add-form" @submit.prevent="addSourcePreference">
                <input v-model="newSourcePreference" class="text-input" placeholder="添加来源偏好" />
                <button class="secondary-button compact" type="submit"><Plus :size="14" /> 添加</button>
              </form>
            </section>
            <section v-if="competitorReuseItems.length">
              <h3>竞品库复用来源</h3>
              <div class="profile-reuse-list">
                <div v-for="item in competitorReuseItems" :key="item.id" class="profile-reuse-row">
                  <strong>{{ item.name }}</strong>
                  <span>{{ item.sourceCountLabel }}</span>
                  <small>{{ item.sourceLabels }}</small>
                </div>
              </div>
            </section>
            <section>
              <h3>搜索关键词</h3>
              <div class="keyword-list">
                <span v-for="item in keywords" :key="item">{{ item }}</span>
              </div>
            </section>
            <section>
              <h3>预算提示</h3>
              <div class="budget-grid">
                <div><strong>{{ displayedBudgetHint.maxSearchRounds }}</strong><span>搜索轮次</span></div>
                <div><strong>{{ displayedBudgetHint.maxSources }}</strong><span>候选来源</span></div>
                <div><strong>{{ displayedBudgetHint.expectedMinutes }}</strong><span>预计分钟</span></div>
              </div>
            </section>
            <section class="risk-note">
              <AlertTriangle :size="18" />
              <p>定价与企业版能力容易出现新旧页面冲突，建议优先验证官方页面和产品文档。</p>
            </section>
          </aside>
        </div>
      </section>

      <section v-else-if="currentPage === 'run'" class="run-page">
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
            <button class="primary-button compact" type="button" @click="go('review')">进入审阅</button>
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
                  <button v-if="canResumeCurrentTask && step.status === 'failed'" class="secondary-button compact" type="button" :disabled="isLoading" @click.stop="resumeTask()">
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
              <h2>可审计事件流</h2>
              <button class="text-button" type="button" @click="refreshCurrentTask"><RefreshCcw :size="15" /> 刷新</button>
            </div>
            <div v-if="auditEvents.length" class="event-list">
              <article v-for="event in auditEvents" :key="event.time + event.text" class="event-row" :class="event.type">
                <span>{{ event.time }}</span>
                <strong>{{ event.type }}</strong>
                <p>{{ event.text }}</p>
                <small v-if="event.detail">{{ event.detail }}</small>
              </article>
            </div>
            <div v-else class="empty-state">暂无执行事件，任务启动后会在这里显示进度。</div>

            <div class="section-header claim-header">
              <h2>结构化 Claim</h2>
              <button class="text-button" type="button" @click="go('review')">查看风险项</button>
            </div>
            <div v-if="claims.length" class="claim-grid">
              <article v-for="claim in claims" :key="claim.id" class="claim-card" :class="[statusClass(claim.status), claim.riskLevel ? `risk-${claim.riskLevel}` : '']">
                <div class="claim-meta">
                  <span>{{ claim.target }} · {{ claim.dimension }}</span>
                  <span>{{ claim.status }}</span>
                  <span v-if="claim.reviewDecision">已审核</span>
                </div>
                <h3>{{ claim.title }}</h3>
                <p>{{ claim.detail }}</p>
                <p v-if="claim.reviewReason" class="review-reason-note">审核理由：{{ claim.reviewReason }}</p>
                <div class="review-quality-row claim-quality-row">
                  <span>置信度 {{ claim.confidenceText || `${claim.confidencePercent ?? 0}% · ${claim.confidence}` }}</span>
                  <span>覆盖率 {{ claim.coverageText || `${claim.coveragePercent ?? 0}%` }}</span>
                  <span>{{ claim.statusText || claim.statusLabel || claim.status }}</span>
                  <span>{{ claim.evidenceText || `${claim.evidence.length} 条 Evidence` }}</span>
                </div>
                <div v-if="claim.qualityFlagLabels?.length" class="claim-quality-flags">
                  <span v-for="flag in claim.qualityFlagLabels" :key="flag">{{ flag }}</span>
                </div>
                <div class="source-compare claim-evidence-list">
                  <button
                    v-for="evidence in claimEvidenceSummaries(claim)"
                    :key="evidence.id || evidence.label"
                    class="evidence-chip"
                    type="button"
                    :disabled="!evidence.id"
                    @click="selectEvidence(evidence.id)"
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
              <div><strong>{{ visibleEvidences.length }}</strong><span>当前证据</span></div>
              <div><strong>{{ visibleEvidences.filter((item) => item.qualityTone === 'high').length }}</strong><span>高质量</span></div>
              <div><strong>{{ evidenceSourceTypeOptions.length - 1 }}</strong><span>来源类型</span></div>
            </div>
            <div class="filter-row">
              <select v-model="evidenceSourceTypeFilter" class="filter-select" :disabled="isLoading" @change="applyEvidenceFilters">
                <option v-for="option in evidenceSourceTypeOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
              <select v-model="evidenceCompetitorFilter" class="filter-select" :disabled="isLoading" @change="applyEvidenceFilters">
                <option v-for="option in evidenceCompetitorOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
              <select v-model="evidenceDimensionFilter" class="filter-select" :disabled="isLoading" @change="applyEvidenceFilters">
                <option v-for="option in evidenceDimensionOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
              </select>
            </div>
            <div v-if="visibleEvidences.length" class="evidence-list evidence-wall-list">
              <button v-for="evidence in visibleEvidences" :key="evidence.id" class="evidence-card evidence-wall-card" :class="evidence.qualityTone" type="button" @click="selectEvidence(evidence.id)">
                <div class="evidence-head">
                  <span class="source-badge" :class="evidence.type">{{ evidence.type }}</span>
                  <strong>{{ evidence.id }}</strong>
                  <small>{{ evidence.confidence }}%</small>
                </div>
                <h3>{{ evidence.title }}</h3>
                <span class="evidence-origin">{{ evidence.wallMeta }}</span>
                <p>{{ evidence.excerpt }}</p>
                <div class="evidence-wall-tags">
                  <span v-for="tag in evidence.claimTags" :key="tag.id">{{ tag.label }}</span>
                  <span v-if="!evidence.claimTags?.length">暂无绑定 Claim</span>
                </div>
                <dl class="evidence-wall-meta">
                  <dt>定位</dt>
                  <dd>{{ evidence.locatorText }}</dd>
                  <dt>绑定</dt>
                  <dd>{{ evidence.claims }} Claim</dd>
                </dl>
              </button>
            </div>
            <div v-else class="empty-state compact-empty">暂无证据，研究完成后会自动沉淀来源与引用片段。</div>
          </aside>
        </div>
      </section>

      <section v-else-if="currentPage === 'review'" class="content-page">
        <header class="page-topbar">
          <div>
            <span class="eyebrow">Evidence review</span>
            <h1>证据审阅</h1>
          </div>
          <div class="topbar-buttons">
            <button v-if="hasContinueResearchRequest" class="secondary-button" type="button" :disabled="isLoading" @click="continueResearch">
              <RefreshCcw :size="17" /> 继续研究
            </button>
            <button class="primary-button" type="button" :disabled="!isReviewCompleted" @click="go('report')">查看报告 <ArrowRight :size="17" /></button>
          </div>
        </header>

        <div class="metric-grid">
          <div><strong>{{ citationCoverage }}%</strong><span>引用覆盖率</span></div>
          <div><strong>{{ claims.filter((claim) => claim.confidence === '高').length }}</strong><span>高置信度结论</span></div>
          <div><strong>{{ claims.filter((claim) => claim.status === '存在冲突').length }}</strong><span>冲突结论</span></div>
          <div><strong>{{ claims.filter((claim) => claim.status === '未披露').length }}</strong><span>未披露项</span></div>
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
                  @click="selectEvidence(evidence.id)"
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
                  v-model="reviewReasons[item.claimId]"
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
              <h3>{{ activeReviewClaim.title }}</h3>
              <p>{{ activeReviewClaim.detail }}</p>
            </div>

            <dl class="review-focus-metrics">
              <div>
                <dt>置信度</dt>
                <dd>{{ activeReviewClaim.confidencePercent ?? 0 }}% · {{ activeReviewClaim.confidence }}</dd>
              </div>
              <div>
                <dt>覆盖率</dt>
                <dd>{{ activeReviewClaim.coveragePercent ?? 0 }}%</dd>
              </div>
              <div>
                <dt>状态</dt>
                <dd>{{ activeReviewClaim.statusLabel || activeReviewClaim.status }}</dd>
              </div>
              <div>
                <dt>Evidence</dt>
                <dd>{{ activeReviewClaim.evidenceSummaries?.length ?? 0 }} 条</dd>
              </div>
            </dl>

            <section v-if="activeReviewClaim.evidenceSummaries?.length" class="review-focus-section">
              <h3>绑定 Evidence</h3>
              <div class="review-focus-evidence">
                <button
                  v-for="evidence in activeReviewClaim.evidenceSummaries"
                  :key="evidence.id || evidence.label"
                  class="evidence-chip"
                  type="button"
                  :disabled="!evidence.id"
                  @click="evidence.id && selectEvidence(evidence.id)"
                >
                  {{ evidence.label }}
                </button>
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
                v-model="reviewReasons[activeReviewClaim.id]"
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
          <button class="primary-button compact" type="button" :disabled="!activeReport" @click="go('report')">查看报告</button>
        </div>
      </section>

      <section v-else-if="currentPage === 'report'" class="report-page">
        <header class="task-topbar">
          <div>
            <span class="eyebrow">Report v{{ activeReport?.version ?? 1 }}</span>
            <h1>{{ currentTaskTitle }}</h1>
          </div>
          <div class="run-metrics">
            <span>引用覆盖率 {{ citationCoverage }}%</span>
            <button class="secondary-button compact" type="button"><ExternalLink :size="16" /> 分享</button>
            <button
              class="secondary-button compact"
              type="button"
              :disabled="!activeReport || !isReviewCompleted || isRegeneratingReport"
              @click="regenerateCurrentReport"
            >
              <RefreshCcw :size="16" /> {{ isRegeneratingReport ? '生成中' : '重新生成' }}
            </button>
            <button
              v-for="item in reportExportFormats"
              :key="item.format"
              :class="item.format === 'markdown' ? 'primary-button compact' : 'secondary-button compact'"
              type="button"
              :disabled="!activeReport || isExporting"
              @click="exportCurrentReport(item.format)"
            >
              <Download :size="16" /> {{ isExporting ? '导出中' : `导出 ${item.label}` }}
            </button>
          </div>
        </header>

        <div v-if="postReviewReportUpdate.hasPostReviewUpdate" class="report-update-banner">
          <div>
            <ShieldCheck :size="17" />
            <span>{{ postReviewReportUpdate.message }}</span>
          </div>
          <button
            v-if="!postReviewReportUpdate.isViewingLatest"
            class="secondary-button compact"
            type="button"
            @click="viewLatestPostReviewReport"
          >
            <ArrowRight :size="15" /> {{ postReviewReportUpdate.actionLabel }}
          </button>
        </div>

        <div class="report-grid">
          <aside class="report-nav">
            <div v-if="reportVersionItems.length" class="report-version-list">
              <span>版本历史</span>
              <button
                v-for="report in reportVersionItems"
                :key="report.id"
                :class="{ active: activeReport?.version === report.version }"
                type="button"
                @click="selectReportVersion(report.version)"
              >
                <strong class="report-version-heading">
                  <span>{{ report.label }}</span>
                  <span v-if="report.isLatest" class="report-version-latest">最新</span>
                </strong>
                <small>{{ report.reasonLabel }} · 覆盖 {{ report.coveragePercent }}%</small>
                <em>{{ report.generatedAtLabel }}</em>
              </button>
            </div>
            <div v-if="reportSections.length" class="report-section-list">
              <span>当前章节</span>
              <button v-for="section in reportSections" :key="section.id" type="button">{{ section.title }}</button>
            </div>
            <template v-else>
              <button class="active" type="button">执行摘要</button>
              <button type="button">竞品概览</button>
              <button type="button">功能对比</button>
              <button type="button">定价分析</button>
              <button type="button">用户口碑</button>
              <button type="button">风险与机会</button>
            </template>
          </aside>

          <article v-if="reportSections.length" class="report-document">
            <h2>{{ currentTaskTitle }}</h2>
            <section v-for="section in reportSections" :key="section.id">
              <h3>{{ section.title }}</h3>
              <pre class="markdown-block">{{ section.content_markdown }}</pre>
              <div v-if="section.evidence?.length" class="section-evidence-list" aria-label="章节证据">
                <div class="section-evidence-heading">
                  <Link2 :size="15" />
                  <span>章节证据</span>
                </div>
                <div v-for="evidence in buildReportSectionEvidenceItems(section)" :key="evidence.id" class="section-evidence-item">
                  <div>
                    <strong>{{ evidence.id }}</strong>
                    <span>{{ evidence.sourceLabel }}</span>
                    <small>{{ evidence.qualityLabel }} · {{ evidence.claimLabel }}</small>
                  </div>
                  <p>{{ evidence.quote }}</p>
                  <a v-if="evidence.sourceUrl" :href="evidence.sourceUrl" target="_blank" rel="noreferrer">
                    <ExternalLink :size="13" /> 来源
                  </a>
                </div>
              </div>
            </section>
          </article>

          <article v-else-if="!taskDetail" class="report-document">
            <h2>Trae 与 AI 编程工具竞品分析</h2>
            <p class="lead">本报告基于公开官网、产品文档、新闻报道和社区讨论，对 Trae、Cursor、GitHub Copilot、Windsurf 进行交叉验证分析。</p>
            <h3>执行摘要</h3>
            <p>
              Cursor 在企业协作和隐私控制方面证据更充分，官方价格页与文档均提到组织级管理能力
              <button class="citation" type="button" @click="selectEvidence('S12')">[S12]</button>
              <button class="citation" type="button" @click="selectEvidence('S18')">[S18]</button>。
            </p>
            <p>Trae 更适合观察其本地化开发工作流和生态整合能力，但企业版公开定价暂未检索到可验证来源，因此应标记为未披露。</p>

            <h3>竞品对比矩阵</h3>
            <table class="compare-table">
              <thead>
                <tr>
                  <th>产品</th>
                  <th>定位</th>
                  <th>优势</th>
                  <th>风险</th>
                  <th>证据</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>Trae</td>
                  <td>AI 原生 IDE</td>
                  <td>本地化体验、完整开发流</td>
                  <td>公开商业化信息不足</td>
                  <td><button class="citation" type="button" @click="selectEvidence('S31')">[S31]</button></td>
                </tr>
                <tr>
                  <td>Cursor</td>
                  <td>AI 代码编辑器</td>
                  <td>企业控制、隐私能力成熟</td>
                  <td>价格敏感用户转化压力</td>
                  <td><button class="citation" type="button" @click="selectEvidence('S12')">[S12]</button></td>
                </tr>
                <tr>
                  <td>GitHub Copilot</td>
                  <td>开发者生态 AI 助手</td>
                  <td>GitHub 生态与企业覆盖</td>
                  <td>IDE 原生体验受限</td>
                  <td><button class="citation" type="button" @click="selectEvidence('S18')">[S18]</button></td>
                </tr>
                <tr>
                  <td>Windsurf</td>
                  <td>Agentic IDE</td>
                  <td>自动化开发体验突出</td>
                  <td>价格来源存在冲突</td>
                  <td><button class="citation" type="button" @click="selectEvidence('S31')">[S31]</button></td>
                </tr>
              </tbody>
            </table>
          </article>

          <article v-else class="report-document empty-report">
            <h2>暂无报告</h2>
            <p class="lead">任务还没有生成报告，完成研究流程后会在这里展示 Markdown 草稿。</p>
          </article>

          <aside class="citation-drawer">
            <div class="drawer-title">
              <Link2 :size="18" />
              <strong>{{ selectedEvidenceDetail.id }}</strong>
            </div>
            <span class="source-badge" :class="selectedEvidenceDetail.type">{{ selectedEvidenceDetail.type }}</span>
            <h2>{{ selectedEvidenceDetail.title }}</h2>
            <p class="domain"><Globe2 :size="15" /> {{ selectedEvidenceDetail.domain }}</p>
            <blockquote>{{ selectedEvidenceDetail.excerpt }}</blockquote>
            <button class="secondary-button compact source-jump-button" type="button" :disabled="!selectedEvidenceDetail.sourceUrl && !selectedEvidenceDetail.canonicalUrl" @click="openEvidenceSource(selectedEvidenceDetail)">
              <ExternalLink :size="15" /> 打开来源
            </button>
            <dl>
              <dt>发布方</dt>
              <dd>{{ selectedEvidenceDetail.publisher }}</dd>
              <dt>原始 URL</dt>
              <dd>{{ selectedEvidenceDetail.sourceUrl || '未记录' }}</dd>
              <dt>Canonical URL</dt>
              <dd>{{ selectedEvidenceDetail.canonicalUrl || '未记录' }}</dd>
              <dt>定位信息</dt>
              <dd>{{ selectedEvidenceDetail.locatorText }}</dd>
              <dt>抽取方式</dt>
              <dd>{{ selectedEvidenceDetail.extractionMethod }}</dd>
              <dt>快照</dt>
              <dd class="snapshot-cell">
                <button
                  class="secondary-button compact snapshot-button"
                  type="button"
                  :disabled="!taskDetail || isSnapshotLoading(selectedEvidenceDetail)"
                  @click="loadEvidenceSnapshot(selectedEvidenceDetail)"
                >
                  <Eye :size="15" /> {{ snapshotButtonLabel(selectedEvidenceDetail) }}
                </button>
                <p class="snapshot-preview">{{ snapshotTextForEvidence(selectedEvidenceDetail) }}</p>
              </dd>
              <dt>发布时间</dt>
              <dd>{{ selectedEvidenceDetail.publishedAt }}</dd>
              <dt>抓取时间</dt>
              <dd>{{ selectedEvidenceDetail.retrievedAt }}</dd>
              <dt>可信度</dt>
              <dd>{{ selectedEvidenceDetail.confidence }}%</dd>
              <dt>关联 Claim</dt>
              <dd>{{ selectedEvidenceDetail.claims }} 个</dd>
            </dl>
            <section v-if="selectedEvidenceDetail.boundClaims?.length" class="bound-claim-section">
              <h3>绑定 Claim</h3>
              <ul class="bound-claim-list">
                <li v-for="claim in selectedEvidenceDetail.boundClaims" :key="claim.id">
                  <strong>{{ claim.label }}</strong>
                  <span>{{ claim.status }}</span>
                  <em>{{ claim.title }}</em>
                </li>
              </ul>
            </section>
          </aside>
        </div>
      </section>

      <section v-else-if="currentPage === 'research'" class="content-page">
        <header class="page-topbar">
          <div>
            <span class="eyebrow">Research library</span>
            <h1>我的调研</h1>
          </div>
          <div class="topbar-buttons">
            <button class="secondary-button" type="button" :disabled="isLoading" @click="resetLocalDemoData"><RefreshCcw :size="17" /> 重置 Demo</button>
            <button class="primary-button" type="button" @click="go('workspace')"><Plus :size="17" /> 新建任务</button>
          </div>
        </header>

        <div class="task-filter-bar">
          <label class="search-field">
            <Search :size="16" />
            <input v-model="taskSearch" type="search" placeholder="搜索任务标题或研究需求" @keyup.enter="applyTaskFilters" />
          </label>
          <div class="segmented-control">
            <button v-for="filter in taskStatusFilters" :key="filter.value" type="button" :class="{ selected: taskStatusFilter === filter.value }" @click="taskStatusFilter = filter.value; applyTaskFilters()">
              {{ filter.label }}
            </button>
          </div>
          <button class="secondary-button compact" type="button" :disabled="isLoading" @click="applyTaskFilters"><RefreshCcw :size="15" /> 刷新</button>
          <button class="text-button" type="button" @click="clearTaskFilters">清空</button>
        </div>

        <div class="task-library-layout">
          <div v-if="recentTasks.length" class="data-table task-table">
            <div class="table-head">
              <span>任务</span>
              <span>状态</span>
              <span>原因</span>
              <span>证据</span>
              <span>Claim</span>
              <span>覆盖率</span>
              <span>操作</span>
            </div>
            <div v-for="task in recentTasks" :key="task.id || task.title" class="table-row" :class="{ selected: taskDetail?.task.id === task.id }">
              <span>
                <strong>{{ task.title }}</strong>
                <small>{{ task.scope }} · {{ task.updatedAt }}</small>
              </span>
              <span><em :class="task.statusTone || statusClass(task.status)">{{ task.status }}</em></span>
              <span class="task-reason">{{ task.statusReason || task.statusDescription || '暂无异常' }}</span>
              <span>{{ task.evidenceCount }}</span>
              <span>{{ task.claimCount }}</span>
              <span>{{ task.coverage }}%</span>
              <span class="task-actions">
                <button class="text-button" type="button" @click="openTask(task)"><Eye :size="15" /> 打开</button>
                <button v-if="task.canResume" class="text-button" type="button" :disabled="isLoading" @click.stop="resumeTask(task)"><RefreshCcw :size="15" /> 继续执行</button>
                <button v-if="task.canRetry" class="text-button" type="button" :disabled="isLoading" @click.stop="retryTask(task)"><RefreshCcw :size="15" /> 重试</button>
                <button v-if="task.canCancel" class="text-button danger-text" type="button" :disabled="isLoading" @click.stop="cancelTask(task)"><Pause :size="15" /> 取消</button>
              </span>
            </div>
          </div>
          <div v-else class="empty-state">暂无调研任务，从工作台输入需求即可创建第一份竞品分析。</div>

          <aside class="task-detail-panel">
            <template v-if="taskDetail && activeTaskSummary">
              <div class="detail-panel-heading">
                <span class="eyebrow">Task detail</span>
                <h2>{{ taskDetail.task.title }}</h2>
                <em :class="activeTaskSummary.statusTone">{{ activeTaskSummary.status }}</em>
              </div>
              <p>{{ activeTaskSummary.statusReason || activeTaskSummary.statusDescription }}</p>
              <div v-if="taskRecoveryFeedback" class="task-recovery-notice" :class="taskRecoveryFeedback.tone">
                <strong>{{ taskRecoveryFeedback.title }}</strong>
                <span>{{ taskRecoveryFeedback.description }}</span>
                <button v-if="taskRecoveryFeedback.primaryAction === 'resume'" class="text-button" type="button" :disabled="isLoading" @click="resumeTask()">
                  <RefreshCcw :size="15" /> 继续执行
                </button>
                <button v-else-if="taskRecoveryFeedback.primaryAction === 'retry'" class="text-button" type="button" :disabled="isLoading" @click="retryTask()">
                  <RefreshCcw :size="15" /> 重试
                </button>
                <button v-else-if="taskRecoveryFeedback.primaryAction === 'cancel'" class="text-button danger-text" type="button" :disabled="isLoading" @click="cancelTask()">
                  <Pause :size="15" /> 取消
                </button>
              </div>
              <dl class="task-detail-grid">
                <dt>当前 run</dt>
                <dd>{{ currentRun?.id || '暂无 run' }}</dd>
                <dt>当前阶段</dt>
                <dd>{{ currentRun?.current_stage || taskDetail.latest_run?.current_stage || '未开始' }}</dd>
                <dt>证据 / Claim</dt>
                <dd>{{ activeTaskSummary.evidenceCount }} / {{ activeTaskSummary.claimCount }}</dd>
                <dt>引用覆盖率</dt>
                <dd>{{ activeTaskSummary.coverage }}%</dd>
              </dl>
              <div class="detail-actions">
                <button class="secondary-button compact" type="button" @click="go('run')"><ListChecks :size="15" /> 过程</button>
                <button class="secondary-button compact" type="button" @click="go('review')"><ClipboardCheck :size="15" /> 审核</button>
                <button class="secondary-button compact" type="button" @click="go('report')"><FileText :size="15" /> 报告</button>
                <button v-if="canResumeCurrentTask" class="secondary-button compact" type="button" :disabled="isLoading" @click="resumeTask()"><RefreshCcw :size="15" /> 继续执行</button>
                <button v-if="canRetryCurrentTask" class="secondary-button compact" type="button" :disabled="isLoading" @click="retryTask()"><RefreshCcw :size="15" /> 重试</button>
                <button v-if="canCancelCurrentTask" class="secondary-button compact danger-button" type="button" :disabled="isLoading" @click="cancelTask()"><Pause :size="15" /> 取消</button>
              </div>
              <div class="run-history">
                <div class="section-header">
                  <h3>Run 历史</h3>
                  <span>{{ runHistory.length }} 次</span>
                </div>
                <div v-if="runHistory.length" class="run-list">
                  <div v-for="run in runHistory" :key="run.id" class="run-row" :class="{ current: run.isCurrent }">
                    <span>
                      <strong>{{ run.label }}</strong>
                      <small>{{ run.id }}</small>
                    </span>
                    <span>{{ run.statusLabel }}</span>
                    <span>{{ run.current_stage }}</span>
                    <small>{{ formatDate(run.started_at || run.queued_at) }}</small>
                    <p v-if="run.reason">{{ run.reason }}</p>
                  </div>
                </div>
                <div v-else class="empty-state compact-empty">该任务还没有 run。</div>
              </div>
            </template>
            <template v-else>
              <span class="eyebrow">Task detail</span>
              <h2>选择任务查看详情</h2>
              <p>任务详情会展示状态原因、当前 run、历史 run，以及失败重试和取消入口。</p>
            </template>
          </aside>
        </div>
      </section>

      <section v-else class="content-page">
        <header class="page-topbar">
          <div>
            <span class="eyebrow">Competitor library</span>
            <h1>竞品库</h1>
          </div>
          <button class="secondary-button" type="button"><Search :size="17" /> 搜索</button>
        </header>
        <div class="competitor-grid">
          <article v-for="row in competitorRows" :key="row.name" class="competitor-card">
            <div>
              <h2>{{ row.name }}</h2>
              <span>{{ row.category }}</span>
            </div>
            <dl>
              <dt>报告</dt>
              <dd>{{ row.reports }}</dd>
              <dt>已验证 Claim</dt>
              <dd>{{ row.verified }}</dd>
              <dt>冲突</dt>
              <dd>{{ row.conflicts }}</dd>
            </dl>
            <p>{{ row.update }}</p>
          </article>
        </div>
      </section>
    </main>

    <aside v-if="currentPage === 'run' && selectedEvidence" class="floating-evidence">
      <button class="close-button" type="button" title="关闭" @click="selectedEvidence = null"><X :size="17" /></button>
      <span class="source-badge" :class="selectedEvidence.type">{{ selectedEvidence.type }}</span>
      <h2>{{ selectedEvidence.id }} · {{ selectedEvidence.title }}</h2>
      <p>{{ selectedEvidence.excerpt }}</p>
      <small>{{ selectedEvidence.domain }} · 可信度 {{ selectedEvidence.confidence }}%</small>
      <dl class="floating-evidence-meta">
        <dt>原始 URL</dt>
        <dd>{{ selectedEvidence.sourceUrl || '未记录' }}</dd>
        <dt>定位</dt>
        <dd>{{ selectedEvidence.locatorText }}</dd>
        <dt>抽取方式</dt>
        <dd>{{ selectedEvidence.extractionMethod }}</dd>
        <dt>快照</dt>
        <dd class="snapshot-cell">
          <button
            class="secondary-button compact snapshot-button"
            type="button"
            :disabled="!taskDetail || isSnapshotLoading(selectedEvidence)"
            @click="loadEvidenceSnapshot(selectedEvidence)"
          >
            <Eye :size="15" /> {{ snapshotButtonLabel(selectedEvidence) }}
          </button>
          <p class="snapshot-preview">{{ snapshotTextForEvidence(selectedEvidence) }}</p>
        </dd>
      </dl>
      <button class="secondary-button compact source-jump-button" type="button" :disabled="!selectedEvidence.sourceUrl && !selectedEvidence.canonicalUrl" @click="openEvidenceSource(selectedEvidence)">
        <ExternalLink :size="15" /> 打开来源
      </button>
    </aside>
  </div>
</template>
