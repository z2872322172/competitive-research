# Structured Task Creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing prompt-only research confirmation flow into a structured task creation screen with editable competitors, dimensions, source preferences, and task metadata.

**Architecture:** Keep the backend task creation API unchanged. Add a focused frontend helper for building a structured payload from the confirmation form, then wire `App.vue` to use that helper and expose editable controls for the fields that already exist in the payload.

**Tech Stack:** Vue 3, TypeScript declarations, Node test runner, existing FastAPI backend contract.

---

### Task 1: Structured Draft Helper Contract

**Files:**
- Modify: `frontend/src/researchTaskDraft.js`
- Modify: `frontend/src/researchTaskDraft.d.ts`
- Modify: `frontend/src/researchTaskDraft.test.mjs`

- [x] **Step 1: Write failing helper tests**

Add tests for `addStructuredDraftItem` and `buildStructuredTaskPayload`. The tests should prove that duplicate chips are removed, whitespace is trimmed, `research_type` still follows prompt-based inference, and the structured payload preserves editable `title`, `report_depth`, `time_range`, `output_format`, `source_preferences`, `competitors`, and `dimensions`.

- [x] **Step 2: Run the helper tests and confirm RED**

Run:

```powershell
cd frontend
node --test src\researchTaskDraft.test.mjs
```

Expected: fail because the new helper exports do not exist yet.

- [x] **Step 3: Implement the helper**

Add `normalizeStructuredList`, `addStructuredDraftItem`, and `buildStructuredTaskPayload` so the confirmation screen can build one canonical payload from local form state. Keep the existing inference helpers intact.

- [x] **Step 4: Run the helper tests and confirm GREEN**

Run:

```powershell
cd frontend
node --test src\researchTaskDraft.test.mjs
```

Expected: all helper tests pass.

### Task 2: Confirmation Screen Wiring

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [x] **Step 1: Add structured form state**

Introduce local state for editable task metadata and list entry fields: task title, report depth, time range, output format, new competitor text, new dimension text, and new source preference text.

- [x] **Step 2: Wire the payload builder**

Replace the inline `buildTaskPayload()` object with a call to `buildStructuredTaskPayload(...)`, passing prompt, title, competitors, dimensions, source preferences, clarification answers, and research weights.

- [x] **Step 3: Make add/remove controls work**

Turn the existing add-chip buttons into real controls that append trimmed, de-duplicated values into the structured lists and clear the input after submission.

- [x] **Step 4: Expose metadata controls**

Add compact controls for report depth, time range, and output format inside the confirmation view so the user can steer the final task before creation.

- [x] **Step 5: Verify the screen builds**

Run:

```powershell
cd frontend
npm run build
```

Expected: build succeeds with no type errors.

### Task 3: Checklist and Validation

**Files:**
- Modify: `智能竞品分析Agent_MVP开发待办清单.md`

- [x] **Step 1: Mark the structured creation items complete**

Update the P7 item for structured task creation once the confirmation screen supports editable metadata, real chip editing, and the new payload builder.

- [x] **Step 2: Record the MVP note**

Add a short note under the relevant stage describing the structured creation flow and the preserved backend contract.

- [x] **Step 3: Run final verification**

Run:

```powershell
cd frontend
node --test src\researchTaskDraft.test.mjs
npm run build
```

Expected: both commands pass.
