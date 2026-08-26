# Stage 7.6A Report Version Regeneration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit report regeneration API and frontend controls for report version history after claim review.

**Architecture:** Reuse existing `create_claim_report(..., force_new_version=True)` and `Report.version` storage. Add a narrow FastAPI endpoint, a pure frontend version-history helper, and small UI wiring in the report page.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, Vue 3, TypeScript, Node test runner.

---

### Task 1: Backend Regenerate Contract

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/api/routes.py`
- Modify: `backend/app/services/research_service.py`

- [ ] **Step 1: Write failing tests**

Add tests for:

- `POST /v1/research-tasks/{task_id}/reports/regenerate` creates version 2 after risky claims are resolved.
- The endpoint returns 409 when unresolved risky claims remain.

- [ ] **Step 2: Run backend tests and verify RED**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py -q`

Expected: FAIL because the route is missing.

- [ ] **Step 3: Implement service guard**

Add a service function that detects unresolved risky claims and raises a route-level 409 condition before generation.

- [ ] **Step 4: Implement route**

Add the POST endpoint. Load task, latest run, and latest report; call existing report generation with `force_new_version=True` and `generation_reason="manual_regenerate"`; return a serialized `ReportOut`.

- [ ] **Step 5: Verify backend GREEN**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py -q`

Expected: PASS.

### Task 2: Frontend Report Version Helper

**Files:**
- Create: `frontend/src/researchReports.js`
- Create: `frontend/src/researchReports.d.ts`
- Create: `frontend/src/researchReports.test.mjs`

- [ ] **Step 1: Write failing helper tests**

Test that report versions are sorted descending for display and include generation reason, generated time, and coverage percent.

- [ ] **Step 2: Run helper test and verify RED**

Run from `frontend`: `node --test src\researchReports.test.mjs`

Expected: FAIL because helper does not exist.

- [ ] **Step 3: Implement helper and declarations**

Add `buildReportVersionItems(reports)` and `selectNewestReportVersion(reports)`.

- [ ] **Step 4: Verify helper GREEN**

Run from `frontend`: `node --test src\researchReports.test.mjs`

Expected: PASS.

### Task 3: Frontend API and UI

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: Add API client**

Add `regenerateReport(taskId: string): Promise<ReportOut>`.

- [ ] **Step 2: Update report types**

Add `input_snapshot` and `generated_at` to frontend `ReportOut`.

- [ ] **Step 3: Wire App.vue**

Use report helper for version items. Add `regenerateCurrentReport()` that calls the API, reloads task detail, and selects the new report version.

- [ ] **Step 4: Add UI**

Add a compact `重新生成` button and richer version-history rows.

- [ ] **Step 5: Add styles**

Style version rows and keep them responsive.

- [ ] **Step 6: Verify frontend**

Run from `frontend`:

```powershell
node --test src\researchReports.test.mjs
npm run build
```

Expected: PASS.

### Task 4: Checklist and Final Verification

**Files:**
- Modify: `智能竞品分析Agent_MVP开发待办清单.md`

- [ ] **Step 1: Mark 7.6A items complete**

Mark report version history, report regeneration, and post-review new version generation as complete.

- [ ] **Step 2: Add 7.6A MVP note**

Document the new API, UI, and unresolved-risk guard.

- [ ] **Step 3: Run final verification**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py -q
cd frontend
node --test src\researchReports.test.mjs
node --test src\researchReview.test.mjs
npm run build
```

Expected: all commands pass.
