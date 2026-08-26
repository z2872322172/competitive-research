# Stage 7.7B Reuse Competitor Profile Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically reuse saved competitor profile sources when creating new research tasks.

**Architecture:** Backend task creation enriches `scope.source_preferences` and records reuse metadata. Frontend confirmation UI reads the task scope and renders compact source reuse hints through a tested helper.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, Vue 3, TypeScript, Node test runner, pytest.

---

### Task 1: Backend Source Reuse

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/services/research_service.py`

- [ ] **Step 1: Write the failing API test**

Add `test_stage_seven_task_creation_reuses_competitor_profile_sources`.

- [ ] **Step 2: Run focused test**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py::test_stage_seven_task_creation_reuses_competitor_profile_sources -q`

Expected: FAIL because task scope does not include reused competitor profile sources.

- [ ] **Step 3: Implement source reuse helper**

Add a helper that matches profiles by competitor name, merges source URLs into `source_preferences`, and records `competitor_profile_reuse`.

- [ ] **Step 4: Run focused test again**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py::test_stage_seven_task_creation_reuses_competitor_profile_sources -q`

Expected: PASS.

### Task 2: Frontend Reuse Hints

**Files:**
- Modify: `frontend/src/researchCompetitors.js`
- Modify: `frontend/src/researchCompetitors.d.ts`
- Modify: `frontend/src/researchCompetitors.test.mjs`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: Write the failing helper test**

Add tests for `buildCompetitorReuseItems(scope)`.

- [ ] **Step 2: Run helper test**

Run: `cd frontend; node --test src\researchCompetitors.test.mjs`

Expected: FAIL because the helper is not exported yet.

- [ ] **Step 3: Implement helper and confirmation UI**

Render reused profile names, source counts, and source labels under research settings.

- [ ] **Step 4: Run frontend tests and build**

Run: `cd frontend; node --test src\researchCompetitors.test.mjs`

Run: `cd frontend; npm run build`

Expected: PASS and build success.

### Task 3: Checklist and Regression

**Files:**
- Modify: `智能竞品分析Agent_MVP开发待办清单.md`

- [ ] **Step 1: Mark reuse item complete**

Mark `支持复用历史竞品研究结果` complete for the 7.7B slice.

- [ ] **Step 2: Run regression checks**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py -q`

Run: `cd frontend; node --test src\researchCompetitors.test.mjs`

Run: `cd frontend; npm run build`

Expected: backend tests pass, helper tests pass, frontend build succeeds.
