# Stage 7.7A Competitor Profile Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist competitor profiles and render the competitor library from backend data.

**Architecture:** Add a small SQLAlchemy model and Pydantic contracts for competitor profiles, expose create/list API routes, and map API rows into the existing Vue competitor library table through a focused frontend helper.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, Vue 3, TypeScript, Node test runner, pytest.

---

### Task 1: Backend Competitor Profile API

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/services/research_service.py`
- Modify: `backend/app/api/routes.py`

- [ ] **Step 1: Write the failing API test**

Add `test_stage_seven_competitor_profiles_persist_sources_and_aggregate_stats`.

- [ ] **Step 2: Run focused test**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py::test_stage_seven_competitor_profiles_persist_sources_and_aggregate_stats -q`

Expected: FAIL because `/v1/competitors` does not exist.

- [ ] **Step 3: Implement model, schemas, service, and routes**

Add `CompetitorProfile`, `CompetitorProfileCreate`, `CompetitorProfileOut`, serializer helpers, `create_competitor_profile`, and `list_competitor_profiles`.

- [ ] **Step 4: Run focused test again**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py::test_stage_seven_competitor_profiles_persist_sources_and_aggregate_stats -q`

Expected: PASS.

### Task 2: Frontend Competitor Library Rows

**Files:**
- Create: `frontend/src/researchCompetitors.js`
- Create: `frontend/src/researchCompetitors.d.ts`
- Create: `frontend/src/researchCompetitors.test.mjs`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Write the failing helper test**

Add tests for `buildCompetitorRows(profiles, fallbackRows)`.

- [ ] **Step 2: Run helper test**

Run: `cd frontend; node --test src\researchCompetitors.test.mjs`

Expected: FAIL because the helper does not exist.

- [ ] **Step 3: Implement helper, API type, and page integration**

Add `listCompetitors()`, load profiles on mount, and use computed rows in the competitor library page.

- [ ] **Step 4: Run frontend tests and build**

Run: `cd frontend; node --test src\researchCompetitors.test.mjs`

Run: `cd frontend; npm run build`

Expected: PASS and build success.

### Task 3: Checklist and Regression

**Files:**
- Modify: `智能竞品分析Agent_MVP开发待办清单.md`

- [ ] **Step 1: Mark Stage 7.7A items complete**

Mark competitor object management and common source storage complete.

- [ ] **Step 2: Run regression checks**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py -q`

Run: `cd frontend; node --test src\researchCompetitors.test.mjs`

Run: `cd frontend; npm run build`

Expected: backend tests pass, helper tests pass, frontend build succeeds.
