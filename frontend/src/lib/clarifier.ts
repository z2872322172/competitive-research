export type ClarificationQuestion = {
  key: string
  label: string
  question: string
  answer: string
  reason?: string
  answerType?: 'free_text' | 'single_choice' | 'multi_choice'
  options?: string[]
  required?: boolean
}

export type ResearchWeight = {
  key: string
  label: string
  value: number
}

export type ClarificationPlan = {
  questions: ClarificationQuestion[]
  weights: ResearchWeight[]
  sourcePreferences: string[]
  budgetHint: {
    maxSearchRounds: number
    maxSources: number
    expectedMinutes: string
  }
}

const DEFAULT_QUESTIONS: ClarificationQuestion[] = [
  {
    key: 'goal',
    label: '研究目标',
    question: '这次研究最终想辅助什么决策？',
    answer: '',
  },
  {
    key: 'scope',
    label: '研究范围',
    question: '研究对象和时间范围是否需要收窄？',
    answer: '',
  },
  {
    key: 'source',
    label: '来源偏好',
    question: '更信任哪些信息来源？',
    answer: '',
  },
  {
    key: 'output',
    label: '输出形式',
    question: '报告更偏战略判断还是可执行清单？',
    answer: '',
  },
]

const WEIGHT_RULES: Array<ResearchWeight & { keywords: string[] }> = [
  { key: 'pricing', label: '定价与商业化', keywords: ['价格', '定价', '套餐', '商业化', 'pricing'], value: 25 },
  { key: 'features', label: '核心功能', keywords: ['功能', '能力', 'feature'], value: 20 },
  { key: 'technology', label: '技术能力', keywords: ['技术', '模型', '性能', '架构'], value: 20 },
  { key: 'sentiment', label: '用户口碑与舆情', keywords: ['口碑', '舆情', '社区', '用户', '评价'], value: 20 },
  { key: 'positioning', label: '产品定位', keywords: ['定位', '竞争格局', '市场', '人群'], value: 15 },
]

function includesAny(text: string, keywords: string[]): boolean {
  const normalized = text.toLowerCase()
  return keywords.some((keyword) => normalized.includes(keyword.toLowerCase()))
}

// 权重只从研究需求的关键词推导：需求没提到的维度不预设，避免编造默认侧重。
function buildWeights(prompt: string): ResearchWeight[] {
  return WEIGHT_RULES.filter((rule) => includesAny(prompt, rule.keywords)).map(({ key, label, value }) => ({ key, label, value }))
}

function buildSourcePreferences(prompt: string): string[] {
  const sources = ['官方网站', '产品文档', '新闻媒体']
  if (includesAny(prompt, ['口碑', '舆情', '社区', '用户', '评价'])) sources.push('社交舆情')
  return sources
}

export function parseManualSourceUrls(input: string): string[] {
  return [
    ...new Set(
      input
        .split(/[\s,，]+/)
        .map((item) => item.trim())
        .filter((item) => /^https?:\/\/\S+$/i.test(item)),
    ),
  ]
}

export function mergeSourcePreferences(preferences: string[], manualUrlInput: string): string[] {
  return [...new Set([...preferences, ...parseManualSourceUrls(manualUrlInput)])]
}

function buildQuestions(): ClarificationQuestion[] {
  // 追问答案留给用户填写，不预填通用话术。
  return DEFAULT_QUESTIONS.map((item) => ({ ...item }))
}

export function buildClarificationPlan(prompt: string): ClarificationPlan {
  const trimmedPrompt = prompt.trim()
  const sourcePreferences = buildSourcePreferences(trimmedPrompt)
  return {
    questions: buildQuestions(),
    weights: buildWeights(trimmedPrompt),
    sourcePreferences,
    budgetHint: {
      maxSearchRounds: sourcePreferences.includes('社交舆情') ? 4 : 3,
      maxSources: sourcePreferences.includes('社交舆情') ? 12 : 9,
      expectedMinutes: sourcePreferences.includes('社交舆情') ? '3-6' : '2-4',
    },
  }
}
