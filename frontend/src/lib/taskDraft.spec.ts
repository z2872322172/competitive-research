import { describe, expect, it } from 'vitest'

import {
  addStructuredDraftItem,
  buildStructuredTaskPayload,
  canStartResearchDraft,
  competitorsForPayload,
  inferResearchType,
  researchTypeForPayload,
} from './taskDraft'

describe('canStartResearchDraft', () => {
  it('allows generic deep research without competitors', () => {
    expect(
      canStartResearchDraft({
        prompt: 'Research enterprise RAG framework selection for internal knowledge bases',
        competitors: [],
        dimensions: [],
      }),
    ).toBe(true)
  })

  it('still blocks empty or too short prompts', () => {
    expect(canStartResearchDraft({ prompt: 'short', competitors: ['Cursor'], dimensions: ['pricing'] })).toBe(false)
    expect(canStartResearchDraft({ prompt: '        ', competitors: ['Cursor'], dimensions: ['pricing'] })).toBe(false)
  })
})

describe('inferResearchType', () => {
  it('keeps competitive template when competitors are present', () => {
    expect(inferResearchType({ prompt: 'Compare Cursor and Copilot pricing', competitors: ['Cursor'] })).toBe('competitive_research')
    expect(inferResearchType({ prompt: 'Research enterprise RAG evaluation', competitors: [] })).toBe('deep_research')
    expect(
      researchTypeForPayload({ prompt: 'Research enterprise RAG evaluation', competitors: [], dimensions: ['architecture', 'risk'] }),
    ).toEqual({
      research_type: 'deep_research',
      template: 'generic_deep_research',
      research_aspects: ['architecture', 'risk'],
    })
  })

  it('ignores default competitor chips for generic deep research prompts', () => {
    const staleDefaultCompetitors = ['Trae', 'Cursor', 'GitHub Copilot', 'Windsurf']

    expect(
      inferResearchType({
        prompt: 'Research how enterprises should evaluate RAG frameworks for internal knowledge bases',
        competitors: staleDefaultCompetitors,
      }),
    ).toBe('deep_research')
    expect(
      competitorsForPayload({
        prompt: 'Research how enterprises should evaluate RAG frameworks for internal knowledge bases',
        competitors: staleDefaultCompetitors,
      }),
    ).toEqual([])
  })
})

describe('explicit research mode', () => {
  it('overrides prompt-based inference for payloads', () => {
    expect(
      researchTypeForPayload({
        prompt: 'Compare Cursor and Copilot pricing',
        competitors: ['Cursor'],
        dimensions: ['pricing'],
        researchMode: 'deep_research',
      }),
    ).toEqual({
      research_type: 'deep_research',
      template: 'generic_deep_research',
      research_aspects: ['pricing'],
    })
    expect(
      competitorsForPayload({
        prompt: 'Compare Cursor and Copilot pricing',
        competitors: ['Cursor'],
        researchMode: 'deep_research',
      }),
    ).toEqual([])
  })
})

describe('addStructuredDraftItem', () => {
  it('trims values and prevents duplicates', () => {
    expect(addStructuredDraftItem(['Cursor'], ' Cursor ')).toEqual(['Cursor'])
    expect(addStructuredDraftItem(['Cursor'], 'GitHub Copilot')).toEqual(['Cursor', 'GitHub Copilot'])
    expect(addStructuredDraftItem(['Cursor'], '   ')).toEqual(['Cursor'])
  })
})

describe('buildStructuredTaskPayload', () => {
  it('preserves editable structured fields', () => {
    const payload = buildStructuredTaskPayload({
      prompt: 'Compare Cursor and GitHub Copilot for enterprise AI coding adoption',
      title: 'Enterprise AI coding comparison',
      competitors: [' Cursor ', 'GitHub Copilot', 'Cursor'],
      dimensions: [' 定价策略 ', '技术能力', '定价策略'],
      sourcePreferences: ['官方来源优先', '产品文档', 'https://cursor.com/pricing'],
      clarificationAnswers: [
        { key: 'goal', label: '研究目标', answer: '判断企业采用优先级' },
        { key: 'output', label: '输出形式', answer: '形成可执行建议' },
      ],
      researchWeights: [
        { label: '定价与商业化', value: 30 },
        { label: '技术能力', value: 25 },
      ],
      researchMode: 'competitive_research',
      reportDepth: 'brief',
      timeRange: 'last_6_months',
      outputFormat: 'battlecard',
    })

    expect(payload.title).toBe('Enterprise AI coding comparison')
    expect(payload.research_type).toBe('competitive_research')
    expect(payload.template).toBe('competitive_research')
    expect(payload.research_question).toBe('Compare Cursor and GitHub Copilot for enterprise AI coding adoption')
    expect(payload.competitors).toEqual(['Cursor', 'GitHub Copilot'])
    expect(payload.dimensions).toEqual(['定价策略', '技术能力'])
    expect(payload.research_aspects).toEqual(['定价策略', '技术能力'])
    expect(payload.source_preferences).toEqual(['官方来源优先', '产品文档', 'https://cursor.com/pricing'])
    expect(payload.report_depth).toBe('brief')
    expect(payload.time_range).toBe('last_6_months')
    expect(payload.output_format).toBe('battlecard')
    expect(payload.prompt).toBe('Compare Cursor and GitHub Copilot for enterprise AI coding adoption')
    expect(payload.clarification_answers).toEqual([
      { key: 'goal', label: '研究目标', answer: '判断企业采用优先级' },
      { key: 'output', label: '输出形式', answer: '形成可执行建议' },
    ])
    expect(payload.research_weights).toEqual([
      { label: '定价与商业化', value: 30 },
      { label: '技术能力', value: 25 },
    ])
  })

  it('can build a generic deep research payload without stale competitors', () => {
    const payload = buildStructuredTaskPayload({
      prompt: 'Research enterprise RAG evaluation criteria for internal knowledge bases',
      competitors: ['Trae', 'Cursor'],
      dimensions: ['架构', '风险'],
      sourcePreferences: ['官方来源优先'],
      researchMode: 'auto',
    })

    expect(payload.research_type).toBe('deep_research')
    expect(payload.template).toBe('generic_deep_research')
    expect(payload.competitors).toEqual([])
    expect(payload.dimensions).toEqual(['架构', '风险'])
  })
})
