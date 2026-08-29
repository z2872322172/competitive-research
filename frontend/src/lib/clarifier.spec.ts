import { describe, expect, it } from 'vitest'

import { buildClarificationPlan, mergeSourcePreferences, parseManualSourceUrls } from './clarifier'

describe('buildClarificationPlan', () => {
  it('turns a research prompt into questions and adjustable weights', () => {
    const plan = buildClarificationPlan(
      '调研 Trae、Cursor、GitHub Copilot 的竞争格局，重点看定价、功能、技术能力和用户口碑，最好抓取舆情。',
    )

    expect(plan.questions.length).toBe(4)
    expect(plan.questions[0].label).toBe('研究目标')
    expect(plan.questions[0].answer).toBe('')
    expect(
      plan.weights.map((item) => [item.key, item.label, item.value]),
    ).toEqual([
      ['pricing', '定价与商业化', 25],
      ['features', '核心功能', 20],
      ['technology', '技术能力', 20],
      ['sentiment', '用户口碑与舆情', 20],
      ['positioning', '产品定位', 15],
    ])
    expect(plan.sourcePreferences.includes('新闻媒体')).toBe(true)
    expect(plan.sourcePreferences.includes('社交舆情')).toBe(true)
    expect(plan.budgetHint.maxSources).toBe(12)
  })

  it('leaves weights empty when the prompt mentions no dimension keywords', () => {
    const plan = buildClarificationPlan('调研一下workbuddy')

    expect(plan.weights).toEqual([])
    expect(plan.questions.every((item) => item.answer === '')).toBe(true)
    expect(plan.sourcePreferences).toEqual(['官方网站', '产品文档', '新闻媒体'])
  })
})

describe('parseManualSourceUrls', () => {
  it('keeps unique http and https URLs from free text', () => {
    expect(
      parseManualSourceUrls(`
      https://cursor.com/pricing, https://docs.github.com/copilot
      not-a-url
      http://example.com/report https://cursor.com/pricing
    `),
    ).toEqual(['https://cursor.com/pricing', 'https://docs.github.com/copilot', 'http://example.com/report'])
  })
})

describe('mergeSourcePreferences', () => {
  it('appends manual URLs without duplicating existing preferences', () => {
    expect(
      mergeSourcePreferences(['官方网站', 'https://cursor.com/pricing'], 'https://cursor.com/pricing\nhttps://trae.ai'),
    ).toEqual(['官方网站', 'https://cursor.com/pricing', 'https://trae.ai'])
  })
})
