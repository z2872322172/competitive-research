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

export type ResearchDraftInput = {
  prompt: string
  competitors: string[]
  dimensions: string[]
  researchMode?: 'auto' | 'competitive_research' | 'deep_research'
}

export type StructuredTaskPayloadInput = ResearchDraftInput & {
  title?: string
  sourcePreferences?: string[]
  researchWeights?: Array<{ label: string; value: number }>
  reportDepth?: string
  timeRange?: string
  outputFormat?: string
  clarificationAnswers?: Array<Record<string, unknown>>
  assumptions?: string[]
}

export type StructuredTaskPayload = {
  prompt: string
  title: string
  research_type: 'competitive_research' | 'deep_research'
  template: 'competitive_research' | 'generic_deep_research'
  research_question: string
  research_aspects: string[]
  competitors: string[]
  dimensions: string[]
  source_preferences: string[]
  report_depth: string
  time_range: string
  output_format: string
  clarification_answers?: Array<Record<string, unknown>>
  research_weights?: Array<Record<string, unknown>>
  assumptions?: string[]
}

export type ResearchTypeMetadata = {
  research_type: 'competitive_research' | 'deep_research'
  template: 'competitive_research' | 'generic_deep_research'
  research_aspects: string[]
}

export function canStartResearchDraft(input: ResearchDraftInput): boolean {
  return input.prompt.trim().length >= MIN_PROMPT_LENGTH
}

function cleanCompetitors(competitors: string[]): string[] {
  return normalizeStructuredList(competitors)
}

export function normalizeStructuredList(items: unknown[] = []): string[] {
  const seen = new Set<string>()
  const result: string[] = []
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

export function addStructuredDraftItem(items: string[] = [], value = ''): string[] {
  return normalizeStructuredList([...items, value])
}

function hasCompetitiveIntent(prompt: string): boolean {
  const normalized = prompt.toLowerCase()
  return COMPETITIVE_INTENT_TERMS.some((term) => normalized.includes(term.toLowerCase()))
}

function promptMentionsAnyCompetitor(prompt: string, competitors: string[]): boolean {
  const normalized = prompt.toLowerCase()
  return competitors.some((item) => normalized.includes(item.toLowerCase()))
}

function normalizeResearchMode(researchMode?: string): 'auto' | 'competitive_research' | 'deep_research' {
  if (researchMode === 'competitive_research' || researchMode === 'deep_research') {
    return researchMode
  }
  return 'auto'
}

export function inferResearchType(input: Pick<ResearchDraftInput, 'prompt' | 'competitors'>): 'competitive_research' | 'deep_research' {
  const cleanedCompetitors = cleanCompetitors(input.competitors)
  if (!cleanedCompetitors.length) return 'deep_research'
  if (hasCompetitiveIntent(input.prompt) || promptMentionsAnyCompetitor(input.prompt, cleanedCompetitors)) return 'competitive_research'
  return 'deep_research'
}

export function competitorsForPayload(input: Pick<ResearchDraftInput, 'prompt' | 'competitors' | 'researchMode'>): string[] {
  const mode = normalizeResearchMode(input.researchMode)
  if (mode === 'deep_research') return []
  return (mode === 'competitive_research' || inferResearchType({ prompt: input.prompt, competitors: input.competitors }) === 'competitive_research')
    ? cleanCompetitors(input.competitors)
    : []
}

export function researchTypeForPayload(input: ResearchDraftInput): ResearchTypeMetadata {
  const mode = normalizeResearchMode(input.researchMode)
  const researchType = mode === 'auto' ? inferResearchType({ prompt: input.prompt, competitors: input.competitors }) : mode
  return {
    research_type: researchType,
    template: researchType === 'competitive_research' ? 'competitive_research' : 'generic_deep_research',
    research_aspects: input.dimensions.map((item) => item.trim()).filter(Boolean),
  }
}

export function buildStructuredTaskPayload(input: StructuredTaskPayloadInput = {} as StructuredTaskPayloadInput): StructuredTaskPayload {
  const trimmedPrompt = (input.prompt ?? '').trim()
  const normalizedDimensions = normalizeStructuredList(input.dimensions)
  const metadata = researchTypeForPayload({
    prompt: trimmedPrompt,
    competitors: input.competitors,
    dimensions: normalizedDimensions,
    researchMode: input.researchMode,
  })
  return {
    prompt: trimmedPrompt,
    title: (input.title ?? '').trim() || trimmedPrompt.slice(0, DEFAULT_TITLE_LENGTH),
    ...metadata,
    research_question: trimmedPrompt,
    competitors: competitorsForPayload({
      prompt: trimmedPrompt,
      competitors: normalizeStructuredList(input.competitors),
      researchMode: input.researchMode,
    }),
    dimensions: normalizedDimensions,
    source_preferences: normalizeStructuredList(input.sourcePreferences),
    report_depth: input.reportDepth ?? 'standard',
    time_range: input.timeRange ?? 'last_12_months',
    output_format: input.outputFormat ?? 'comprehensive_report',
    clarification_answers: input.clarificationAnswers ?? [],
    research_weights: (input.researchWeights ?? [])
      .map((item) => ({
        label: String(item.label ?? '').trim(),
        value: Number(item.value),
      }))
      .filter((item) => item.label && Number.isFinite(item.value)),
    assumptions: input.assumptions ?? [],
  }
}
