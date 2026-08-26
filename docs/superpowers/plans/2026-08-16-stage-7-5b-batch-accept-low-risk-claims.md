# Stage 7.5B Batch Accept Low-Risk Claims Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a review-page bulk action that accepts low-risk claims through the existing claim review API.

**Architecture:** Keep risk selection in `frontend/src/researchReview.js` as a pure helper, then consume it in `frontend/src/App.vue`. The UI submits existing single-claim review requests sequentially and refreshes task state after completion.

**Tech Stack:** Vue 3, TypeScript, Node test runner, existing frontend API client.

---

### Task 1: Low-Risk Candidate Helper

**Files:**
- Modify: `frontend/src/researchReview.test.mjs`
- Modify: `frontend/src/researchReview.js`
- Modify: `frontend/src/researchReview.d.ts`

- [ ] **Step 1: Write the failing test**

Add tests that import `buildLowRiskReviewCandidates` and assert the rule:

```js
test('buildLowRiskReviewCandidates returns only safe unreviewed verified claims', () => {
  const candidates = buildLowRiskReviewCandidates([
    { id: 'safe', status: 'verified', confidence_score: 0.86, evidence_coverage: 0.91, include_in_report: true, evidence_ids: ['ev-1'], review_decision: null },
    { id: 'continue-safe', status: 'verified', confidence_score: 0.8, evidence_coverage: 0.8, include_in_report: true, evidence_ids: ['ev-1'], review_decision: 'continue_research' },
    { id: 'conflict', status: 'conflict', confidence_score: 0.95, evidence_coverage: 1, include_in_report: true, evidence_ids: ['ev-1'], review_decision: null },
    { id: 'excluded', status: 'verified', confidence_score: 0.95, evidence_coverage: 1, include_in_report: false, evidence_ids: ['ev-1'], review_decision: null },
    { id: 'accepted', status: 'verified', confidence_score: 0.95, evidence_coverage: 1, include_in_report: true, evidence_ids: ['ev-1'], review_decision: 'accept' },
    { id: 'weak', status: 'verified', confidence_score: 0.79, evidence_coverage: 1, include_in_report: true, evidence_ids: ['ev-1'], review_decision: null },
    { id: 'no-evidence', status: 'verified', confidence_score: 0.95, evidence_coverage: 1, include_in_report: true, evidence_ids: [], review_decision: null },
  ])

  assert.deepEqual(candidates.map((item) => item.claimId), ['safe', 'continue-safe'])
  assert.equal(candidates[0].reason, '批量接受：低风险 Claim 已达到置信度和引用覆盖率阈值。')
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test src\researchReview.test.mjs` from `frontend`.

Expected: FAIL because `buildLowRiskReviewCandidates` is not exported.

- [ ] **Step 3: Implement the helper**

Add `LOW_RISK_REVIEW_REASON`, threshold constants, and `buildLowRiskReviewCandidates(claims)` in `researchReview.js`.

- [ ] **Step 4: Add TypeScript declaration**

Declare `LowRiskReviewCandidate` and `buildLowRiskReviewCandidates` in `researchReview.d.ts`.

- [ ] **Step 5: Run helper tests**

Run: `node --test src\researchReview.test.mjs` from `frontend`.

Expected: PASS.

### Task 2: Review Page Bulk Action

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: Import helper**

Import `buildLowRiskReviewCandidates` alongside the existing review helpers.

- [ ] **Step 2: Add computed candidates**

Add `lowRiskReviewCandidates = computed(() => taskDetail.value ? buildLowRiskReviewCandidates(taskDetail.value.claims) : [])`.

- [ ] **Step 3: Add click handler**

Add `handleBatchAcceptLowRiskClaims()` that loops candidates, calls `reviewClaim(candidate.claimId, 'accept', candidate.reason)`, then reloads task detail and task list.

- [ ] **Step 4: Add UI control**

Add a compact review toolbar above the tabs with a primary button, count text, and disabled states.

- [ ] **Step 5: Add CSS**

Add `.review-action-bar` styles that match existing compact controls and stay responsive.

- [ ] **Step 6: Run frontend verification**

Run from `frontend`:

```powershell
node --test src\researchReview.test.mjs
npm run build
```

Expected: both commands pass.

### Task 3: Checklist Update

**Files:**
- Modify: `智能竞品分析Agent_MVP开发待办清单.md`

- [ ] **Step 1: Mark item complete**

Change the Stage 7.5 batch acceptance item from unchecked to checked.

- [ ] **Step 2: Add short MVP note**

Append a 7.5B note that the UI now bulk-accepts verified low-risk claims through the existing single-claim review API.

- [ ] **Step 3: Final verification**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py -q
cd frontend
node --test src\researchReview.test.mjs
node --test src\researchEvidence.test.mjs
npm run build
```

Expected: backend contract tests, frontend helper tests, evidence tests, and frontend build pass.
