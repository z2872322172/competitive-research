const DEFAULT_QUESTIONS = [
  {
    key: 'goal',
    label: '研究目标',
    question: '这次研究最终想辅助什么决策？',
    answer: '判断竞争格局、机会风险和下一步产品策略。',
  },
  {
    key: 'scope',
    label: '研究范围',
    question: '研究对象和时间范围是否需要收窄？',
    answer: '优先覆盖需求中提到的竞品，时间范围默认最近 12 个月。',
  },
  {
    key: 'source',
    label: '来源偏好',
    question: '更信任哪些信息来源？',
    answer: '优先官网、产品文档和新闻媒体；舆情作为辅助判断。',
  },
  {
    key: 'output',
    label: '输出形式',
    question: '报告更偏战略判断还是可执行清单？',
    answer: '输出综合报告，包含证据、Claim 审核点和行动建议。',
  },
]

const WEIGHT_RULES = [
  { key: 'pricing', label: '定价与商业化', keywords: ['价格', '定价', '套餐', '商业化', 'pricing'], value: 25 },
  { key: 'features', label: '核心功能', keywords: ['功能', '能力', 'feature'], value: 20 },
  { key: 'technology', label: '技术能力', keywords: ['技术', '模型', '性能', '架构'], value: 20 },
  { key: 'sentiment', label: '用户口碑与舆情', keywords: ['口碑', '舆情', '社区', '用户', '评价'], value: 20 },
  { key: 'positioning', label: '产品定位', keywords: ['定位', '竞争格局', '市场', '人群'], value: 15 },
]

function includesAny(text, keywords) {
  const normalized = text.toLowerCase()
  return keywords.some((keyword) => normalized.includes(keyword.toLowerCase()))
}

function buildWeights(prompt) {
  const matched = WEIGHT_RULES.filter((rule) => includesAny(prompt, rule.keywords))
  if (matched.length >= 3) return matched

  const withFallbacks = [...matched]
  for (const rule of WEIGHT_RULES) {
    if (withFallbacks.length >= 5) break
    if (!withFallbacks.some((item) => item.key === rule.key)) withFallbacks.push(rule)
  }
  return withFallbacks
}

function buildSourcePreferences(prompt) {
  const sources = ['官方网站', '产品文档', '新闻媒体']
  if (includesAny(prompt, ['口碑', '舆情', '社区', '用户', '评价'])) sources.push('社交舆情')
  return sources
}

export function parseManualSourceUrls(input) {
  return [
    ...new Set(
      input
        .split(/[\s,，]+/)
        .map((item) => item.trim())
        .filter((item) => /^https?:\/\/\S+$/i.test(item)),
    ),
  ]
}

export function mergeSourcePreferences(preferences, manualUrlInput) {
  return [...new Set([...preferences, ...parseManualSourceUrls(manualUrlInput)])]
}

function buildQuestions(prompt) {
  const questions = DEFAULT_QUESTIONS.map((item) => ({ ...item }))
  if (includesAny(prompt, ['竞争格局', '竞品', '对比'])) {
    questions[0].answer = '判断竞争格局、关键差异、机会风险和可执行策略。'
  }
  if (includesAny(prompt, ['舆情', '口碑', '社区'])) {
    questions[2].answer = '官网和文档作为事实基线，新闻和社交舆情用于补充市场反馈。'
  }
  return questions
}

export function buildClarificationPlan(prompt) {
  const trimmedPrompt = prompt.trim()
  const sourcePreferences = buildSourcePreferences(trimmedPrompt)
  return {
    questions: buildQuestions(trimmedPrompt),
    weights: buildWeights(trimmedPrompt),
    sourcePreferences,
    budgetHint: {
      maxSearchRounds: sourcePreferences.includes('社交舆情') ? 4 : 3,
      maxSources: sourcePreferences.includes('社交舆情') ? 12 : 9,
      expectedMinutes: sourcePreferences.includes('社交舆情') ? '3-6' : '2-4',
    },
  }
}
