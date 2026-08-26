# Main Research Line Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tighten the main research flow so claims show quality judgment in the workbench and review actions reliably land on refreshed report versions.

**Architecture:** Keep the existing backend review/report lifecycle intact and add a small shared front-end claim-quality helper. The workbench claim cards and review cards will read from the same quality snapshot so confidence, coverage, status, and evidence bindings stay consistent across views.

**Tech Stack:** FastAPI, SQLAlchemy, Vue 3, TypeScript, node:test

---

### Task 1: Shared claim-quality helper

**Files:**
- Modify: `frontend/src/researchReview.js`
- Test: `frontend/src/researchReview.test.mjs`

- [ ] **Step 1: Write the failing test**

```js
test('buildClaimQualitySnapshot exposes confidence, coverage, status, and evidence bindings', () => {
  const result = buildClaimQualitySnapshot(
    {
      id: 'claim-1',
      status: 'conflict',
      confidence_score: 0.62,
      evidence_coverage: 0.5,
      evidence_ids: ['ev-1', 'ev-2'],
    },
    [
      { id: 'ev-1', type: '官方', confidence: 86, title: 'Cursor Pricing' },
      { id: 'ev-2', type: '新闻', confidence: 54, title: 'Market Update' },
    ],
  )

  assert.equal(result.confidencePercent, 62)
  assert.equal(result.coveragePercent, 50)
  assert.equal(result.statusLabel, '存在冲突')
  assert.deepEqual(result.evidenceSummaries.map((item) => item.label), [
    'ev-1 · 官方 · 86% · Cursor Pricing',
    'ev-2 · 新闻 · 54% · Market Update',
  ])
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test frontend/src/researchReview.test.mjs`
Expected: FAIL because `buildClaimQualitySnapshot` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add `buildClaimQualitySnapshot(claim, evidences)` and reuse it from `buildReviewItems`.

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test frontend/src/researchReview.test.mjs`
Expected: PASS

### Task 2: Workbench claim quality UI

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: Update the workbench claim card to show claim quality**

Use the shared claim-quality helper so each claim card shows confidence, coverage, status, and evidence count.

- [ ] **Step 2: Add compact styles for the new quality row**

Keep the layout dense and readable in both desktop and mobile breakpoints.

- [ ] **Step 3: Run the frontend build**

Run: `npm run build` from `frontend/`
Expected: PASS

### Task 3: Review and report refresh flow

**Files:**
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Keep review actions on the refreshed latest report version**

After a review decision or report regeneration, keep the latest report selected and move the user into the report view when review is complete.

- [ ] **Step 2: Run the frontend build again**

Run: `npm run build` from `frontend/`
Expected: PASS

