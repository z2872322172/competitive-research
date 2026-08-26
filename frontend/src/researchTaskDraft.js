const MIN_PROMPT_LENGTH = 8
const DEFAULT_TITLE_LENGTH = 48
const COMPETITIVE_INTENT_TERMS = [
  'compare',
  'comparison',
  'competitor',
  'competitive',
  'competition',
  'rival',
  'versus',
  'swot',
  'landscape',
  '对比',
  '竞品',
  '竞争',
  '格局',
]

export function canStartResearchDraft({ prompt }) {
  return prompt.trim().length >= MIN_PROMPT_LENGTH
}

function cleanCompetitors(competitors) {
  return normalizeStructuredList(competitors)
}

export function normalizeStructuredList(items = []) {
  const seen = new Set()
  const result = []
  for (const rawItem of items) {
    const item = String(rawItem ?? '').trim()
    if (!item) continue
    const key = item.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    result.push(item)
  }
  return result
}

export function addStructuredDraftItem(items = [], value = '') {
  return normalizeStructuredList([...items, value])
}

function hasCompetitiveIntent(prompt) {
  const normalized = prompt.toLowerCase()
  return COMPETITIVE_INTENT_TERMS.some((term) => normalized.includes(term.toLowerCase()))
}

function promptMentionsAnyCompetitor(prompt, competitors) {
  const normalized = prompt.toLowerCase()
  return competitors.some((item) => normalized.includes(item.toLowerCase()))
}

function normalizeResearchMode(researchMode) {
  if (researchMode === 'competitive_research' || researchMode === 'deep_research') {
    return researchMode
  }
  return 'auto'
}

export function inferResearchType({ prompt = '', competitors }) {
  const cleanedCompetitors = cleanCompetitors(competitors)
  if (!cleanedCompetitors.length) return 'deep_research'
  if (hasCompetitiveIntent(prompt) || promptMentionsAnyCompetitor(prompt, cleanedCompetitors)) return 'competitive_research'
  return 'deep_research'
}

export function competitorsForPayload({ prompt = '', competitors, researchMode }) {
  const mode = normalizeResearchMode(researchMode)
  if (mode === 'deep_research') return []
  return (mode === 'competitive_research' || inferResearchType({ prompt, competitors }) === 'competitive_research')
    ? cleanCompetitors(competitors)
    : []
}

export function researchTypeForPayload({ prompt = '', competitors, dimensions, researchMode }) {
  const mode = normalizeResearchMode(researchMode)
  const researchType = mode === 'auto' ? inferResearchType({ prompt, competitors }) : mode
  return {
    research_type: researchType,
    template: researchType === 'competitive_research' ? 'competitive_research' : 'generic_deep_research',
    research_aspects: dimensions.map((item) => item.trim()).filter(Boolean),
  }
}

function buildClarificationContext(questions = [], weights = []) {
  const lines = []
  const answeredQuestions = questions
    .map((item) => ({
      label: String(item.label ?? '').trim(),
      answer: String(item.answer ?? '').trim(),
    }))
    .filter((item) => item.label && item.answer)
  if (answeredQuestions.length) {
    lines.push('澄清问题：')
    lines.push(...answeredQuestions.map((item) => `- ${item.label}：${item.answer}`))
  }

  const validWeights = weights
    .map((item) => ({
      label: String(item.label ?? '').trim(),
      value: Number(item.value),
    }))
    .filter((item) => item.label && Number.isFinite(item.value))
  if (validWeights.length) {
    lines.push('研究权重：')
    lines.push(...validWeights.map((item) => `- ${item.label} ${item.value}%`))
  }
  return lines.join('\n')
}

export function buildStructuredTaskPayload({
  prompt = '',
  title = '',
  competitors = [],
  dimensions = [],
  sourcePreferences = [],
  clarificationQuestions = [],
  researchWeights = [],
  researchMode = 'auto',
  reportDepth = 'standard',
  timeRange = 'last_12_months',
  outputFormat = 'comprehensive_report',
} = {}) {
  const trimmedPrompt = prompt.trim()
  const normalizedDimensions = normalizeStructuredList(dimensions)
  const metadata = researchTypeForPayload({
    prompt: trimmedPrompt,
    competitors,
    dimensions: normalizedDimensions,
    researchMode,
  })
  const clarificationContext = buildClarificationContext(clarificationQuestions, researchWeights)
  return {
    prompt: clarificationContext ? `${trimmedPrompt}\n\n${clarificationContext}` : trimmedPrompt,
    title: title.trim() || trimmedPrompt.slice(0, DEFAULT_TITLE_LENGTH),
    ...metadata,
    research_question: trimmedPrompt,
    competitors: competitorsForPayload({
      prompt: trimmedPrompt,
      competitors: normalizeStructuredList(competitors),
      researchMode,
    }),
    dimensions: normalizedDimensions,
    source_preferences: normalizeStructuredList(sourcePreferences),
    report_depth: reportDepth,
    time_range: timeRange,
    output_format: outputFormat,
  }
}
