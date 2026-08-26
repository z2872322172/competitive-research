import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  addStructuredDraftItem,
  buildStructuredTaskPayload,
  canStartResearchDraft,
  competitorsForPayload,
  inferResearchType,
  researchTypeForPayload,
} from './researchTaskDraft.js'

test('canStartResearchDraft allows generic deep research without competitors', () => {
  assert.equal(
    canStartResearchDraft({
      prompt: 'Research enterprise RAG framework selection for internal knowledge bases',
      competitors: [],
      dimensions: [],
    }),
    true,
  )
})

test('canStartResearchDraft still blocks empty or too short prompts', () => {
  assert.equal(canStartResearchDraft({ prompt: 'short', competitors: ['Cursor'], dimensions: ['pricing'] }), false)
  assert.equal(canStartResearchDraft({ prompt: '        ', competitors: ['Cursor'], dimensions: ['pricing'] }), false)
})

test('inferResearchType keeps competitive template when competitors are present', () => {
  assert.equal(inferResearchType({ prompt: 'Compare Cursor and Copilot pricing', competitors: ['Cursor'] }), 'competitive_research')
  assert.equal(inferResearchType({ prompt: 'Research enterprise RAG evaluation', competitors: [] }), 'deep_research')
  assert.deepEqual(
    researchTypeForPayload({ prompt: 'Research enterprise RAG evaluation', competitors: [], dimensions: ['architecture', 'risk'] }),
    {
      research_type: 'deep_research',
      template: 'generic_deep_research',
      research_aspects: ['architecture', 'risk'],
    },
  )
})

test('default competitor chips are ignored for generic deep research prompts', () => {
  const staleDefaultCompetitors = ['Trae', 'Cursor', 'GitHub Copilot', 'Windsurf']

  assert.equal(
    inferResearchType({
      prompt: 'Research how enterprises should evaluate RAG frameworks for internal knowledge bases',
      competitors: staleDefaultCompetitors,
    }),
    'deep_research',
  )
  assert.deepEqual(
    competitorsForPayload({
      prompt: 'Research how enterprises should evaluate RAG frameworks for internal knowledge bases',
      competitors: staleDefaultCompetitors,
    }),
    [],
  )
})

test('explicit research mode overrides prompt-based inference for payloads', () => {
  assert.deepEqual(
    researchTypeForPayload({
      prompt: 'Compare Cursor and Copilot pricing',
      competitors: ['Cursor'],
      dimensions: ['pricing'],
      researchMode: 'deep_research',
    }),
    {
      research_type: 'deep_research',
      template: 'generic_deep_research',
      research_aspects: ['pricing'],
    },
  )
  assert.deepEqual(
    competitorsForPayload({
      prompt: 'Compare Cursor and Copilot pricing',
      competitors: ['Cursor'],
      researchMode: 'deep_research',
    }),
    [],
  )
})

test('addStructuredDraftItem trims values and prevents duplicates', () => {
  assert.deepEqual(addStructuredDraftItem(['Cursor'], ' Cursor '), ['Cursor'])
  assert.deepEqual(addStructuredDraftItem(['Cursor'], 'GitHub Copilot'), ['Cursor', 'GitHub Copilot'])
  assert.deepEqual(addStructuredDraftItem(['Cursor'], '   '), ['Cursor'])
})

test('buildStructuredTaskPayload preserves editable structured fields', () => {
  const payload = buildStructuredTaskPayload({
    prompt: 'Compare Cursor and GitHub Copilot for enterprise AI coding adoption',
    title: 'Enterprise AI coding comparison',
    competitors: [' Cursor ', 'GitHub Copilot', 'Cursor'],
    dimensions: [' 定价策略 ', '技术能力', '定价策略'],
    sourcePreferences: ['官方来源优先', '产品文档', 'https://cursor.com/pricing'],
    clarificationQuestions: [
      { label: '研究目标', answer: '判断企业采用优先级' },
      { label: '输出形式', answer: '形成可执行建议' },
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

  assert.equal(payload.title, 'Enterprise AI coding comparison')
  assert.equal(payload.research_type, 'competitive_research')
  assert.equal(payload.template, 'competitive_research')
  assert.equal(payload.research_question, 'Compare Cursor and GitHub Copilot for enterprise AI coding adoption')
  assert.deepEqual(payload.competitors, ['Cursor', 'GitHub Copilot'])
  assert.deepEqual(payload.dimensions, ['定价策略', '技术能力'])
  assert.deepEqual(payload.research_aspects, ['定价策略', '技术能力'])
  assert.deepEqual(payload.source_preferences, ['官方来源优先', '产品文档', 'https://cursor.com/pricing'])
  assert.equal(payload.report_depth, 'brief')
  assert.equal(payload.time_range, 'last_6_months')
  assert.equal(payload.output_format, 'battlecard')
  assert.match(payload.prompt, /研究目标：判断企业采用优先级/)
  assert.match(payload.prompt, /定价与商业化 30%/)
})

test('buildStructuredTaskPayload can build a generic deep research payload without stale competitors', () => {
  const payload = buildStructuredTaskPayload({
    prompt: 'Research enterprise RAG evaluation criteria for internal knowledge bases',
    competitors: ['Trae', 'Cursor'],
    dimensions: ['架构', '风险'],
    sourcePreferences: ['官方来源优先'],
    researchMode: 'auto',
  })

  assert.equal(payload.research_type, 'deep_research')
  assert.equal(payload.template, 'generic_deep_research')
  assert.deepEqual(payload.competitors, [])
  assert.deepEqual(payload.dimensions, ['架构', '风险'])
})
