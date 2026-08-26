export type ClarificationQuestion = {
  key: string
  label: string
  question: string
  answer: string
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

export function buildClarificationPlan(prompt: string): ClarificationPlan
export function parseManualSourceUrls(input: string): string[]
export function mergeSourcePreferences(preferences: string[], manualUrlInput: string): string[]
