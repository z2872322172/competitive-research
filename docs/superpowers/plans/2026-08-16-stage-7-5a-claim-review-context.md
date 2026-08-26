# Stage 7.5A Claim Review Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show Claim quality context and user-entered review reasons in the existing Claim review workflow.

**Architecture:** Keep the backend review API unchanged. Add a focused frontend helper module that maps `ClaimOut` plus Evidence view models into review cards, then wire `App.vue` to render quality metadata, Evidence chips, and per-Claim reason textareas.

**Tech Stack:** Vue 3, TypeScript, Node test runner, FastAPI contract tests for regression.

---

### Task 1: Review Helper Contract

**Files:**
- Create: `frontend/src/researchReview.js`
- Create: `frontend/src/researchReview.d.ts`
- Create: `frontend/src/researchReview.test.mjs`

- [x] **Step 1: Write failing helper tests**

Create tests for `buildReviewItems` and `resolveReviewReason`. The tests should assert that risky unresolved Claims become review items with `confidencePercent`, `coveragePercent`, `statusLabel`, and Evidence summaries, and that typed reasons override default recommendations.

- [x] **Step 2: Run targeted helper tests and confirm RED**

Run:

```powershell
cd frontend
node --test src\researchReview.test.mjs
```

Expected: fails because `researchReview.js` does not exist.

- [x] **Step 3: Implement review helper module**

Create `buildReviewItems(claims, evidences)` and `resolveReviewReason(item, typedReason)`. The helper should keep `continue_research` items visible, hide processed accept/exclude/mark_uncertain items, and produce Evidence summaries from Evidence view models by id.

- [x] **Step 4: Run targeted helper tests and confirm GREEN**

Run:

```powershell
cd frontend
node --test src\researchReview.test.mjs
```

Expected: all review helper tests pass.

### Task 2: Review UI Integration

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [x] **Step 1: Wire helper into App.vue**

Import `buildReviewItems` and `resolveReviewReason`, replace inline `reviewItems` mapping, and add `reviewReasons` state keyed by Claim id.

- [x] **Step 2: Render quality metadata and Evidence chips**

In each review card, show confidence score, citation coverage, status label, and bound Evidence buttons. Add a textarea for the review reason and pass the resolved reason to `reviewClaim`.

- [x] **Step 3: Run frontend verification**

Run:

```powershell
cd frontend
node --test src\researchReview.test.mjs
node --test src\researchEvidence.test.mjs
npm run build
```

Expected: helper tests and production build pass.

### Task 3: Regression and Checklist Update

**Files:**
- Modify: `智能竞品分析Agent_MVP开发待办清单.md`
- Modify: `docs/superpowers/plans/2026-08-16-stage-7-5a-claim-review-context.md`

- [x] **Step 1: Run backend regression**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py -q
```

Expected: existing backend API contracts remain green.

- [x] **Step 2: Mark completed checklist items**

Mark the relevant Stage 7.5 items complete: Claim review interaction, exclusion with reason, uncertain marking, bound Evidence list, and Claim confidence/coverage/status display. Leave bulk accept unchecked.

- [x] **Step 3: Record verification**

Check off this plan after all verification commands pass. No git commit is possible because the workspace is not a git repository.
