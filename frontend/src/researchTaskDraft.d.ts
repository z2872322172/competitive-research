export type ResearchDraftInput = {
  prompt: string
  competitors: string[]
  dimensions: string[]
  researchMode?: 'auto' | 'competitive_research' | 'deep_research'
}

export type StructuredTaskPayloadInput = ResearchDraftInput & {
  title?: string
  sourcePreferences?: string[]
  clarificationQuestions?: Array<{ label: string; answer: string }>
  researchWeights?: Array<{ label: string; value: number }>
  reportDepth?: string
  timeRange?: string
  outputFormat?: string
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
}

export function canStartResearchDraft(input: ResearchDraftInput): boolean

export function inferResearchType(input: Pick<ResearchDraftInput, 'prompt' | 'competitors'>): 'competitive_research' | 'deep_research'

export function competitorsForPayload(input: Pick<ResearchDraftInput, 'prompt' | 'competitors' | 'researchMode'>): string[]

export function researchTypeForPayload(input: ResearchDraftInput): {
  research_type: 'competitive_research' | 'deep_research'
  template: 'competitive_research' | 'generic_deep_research'
  research_aspects: string[]
}

export function normalizeStructuredList(items?: unknown[]): string[]

export function addStructuredDraftItem(items?: string[], value?: string): string[]

export function buildStructuredTaskPayload(input?: StructuredTaskPayloadInput): StructuredTaskPayload
