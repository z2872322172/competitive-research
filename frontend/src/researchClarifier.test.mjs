import assert from 'node:assert/strict'
import { test } from 'node:test'

import { buildClarificationPlan, mergeSourcePreferences, parseManualSourceUrls } from './researchClarifier.js'

test('buildClarificationPlan turns a research prompt into questions and adjustable weights', () => {
  const plan = buildClarificationPlan(
    '调研 Trae、Cursor、GitHub Copilot 的竞争格局，重点看定价、功能、技术能力和用户口碑，最好抓取舆情。',
  )

  assert.equal(plan.questions.length, 4)
  assert.equal(plan.questions[0].label, '研究目标')
  assert.ok(plan.questions[0].answer.includes('竞争格局'))
  assert.deepEqual(
    plan.weights.map((item) => [item.key, item.label, item.value]),
    [
      ['pricing', '定价与商业化', 25],
      ['features', '核心功能', 20],
      ['technology', '技术能力', 20],
      ['sentiment', '用户口碑与舆情', 20],
      ['positioning', '产品定位', 15],
    ],
  )
  assert.ok(plan.sourcePreferences.includes('新闻媒体'))
  assert.ok(plan.sourcePreferences.includes('社交舆情'))
  assert.equal(plan.budgetHint.maxSources, 12)
})

test('parseManualSourceUrls keeps unique http and https URLs from free text', () => {
  assert.deepEqual(
    parseManualSourceUrls(`
      https://cursor.com/pricing, https://docs.github.com/copilot
      not-a-url
      http://example.com/report https://cursor.com/pricing
    `),
    ['https://cursor.com/pricing', 'https://docs.github.com/copilot', 'http://example.com/report'],
  )
})

test('mergeSourcePreferences appends manual URLs without duplicating existing preferences', () => {
  assert.deepEqual(
    mergeSourcePreferences(['官方网站', 'https://cursor.com/pricing'], 'https://cursor.com/pricing\nhttps://trae.ai'),
    ['官方网站', 'https://cursor.com/pricing', 'https://trae.ai'],
  )
})
