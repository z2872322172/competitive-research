# Stage 7.6B Section Evidence Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show Evidence tied to each report section so generated reports are traceable at chapter level.

**Architecture:** The backend stores a section evidence snapshot in `input_snapshot.report_generation.section_evidence` and serializes it on each `ReportSectionOut`. The frontend formats those per-section snapshots with a small helper and renders them directly below section markdown.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, Vue 3, TypeScript, Node test runner, pytest.

---

### Task 1: Backend API Contract

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/services/reporting.py`
- Modify: `backend/app/services/research_service.py`

- [ ] **Step 1: Write the failing API test**

Add a test that confirms report sections include an `evidence` array with source and quote snapshots.

- [ ] **Step 2: Run the focused test**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py::test_stage_seven_report_sections_include_citation_evidence -q`

Expected: FAIL because `section["evidence"]` does not exist yet.

- [ ] **Step 3: Implement section evidence snapshots**

Add `ReportSectionEvidenceOut`, add `evidence` to `ReportSectionOut`, build `section_evidence` during report generation, and serialize snapshots onto sections.

- [ ] **Step 4: Run the focused test again**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py::test_stage_seven_report_sections_include_citation_evidence -q`

Expected: PASS.

### Task 2: Frontend Section Evidence Display

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/researchReports.js`
- Modify: `frontend/src/researchReports.d.ts`
- Modify: `frontend/src/researchReports.test.mjs`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [ ] **Step 1: Write the failing helper test**

Add a Node test for `buildReportSectionEvidenceItems(section)` that verifies labels, source fallback, quality percentage, and empty input.

- [ ] **Step 2: Run the helper test**

Run: `cd frontend; node --test src\researchReports.test.mjs`

Expected: FAIL because the helper is not exported yet.

- [ ] **Step 3: Implement helper and UI**

Add frontend types for section evidence, implement `buildReportSectionEvidenceItems`, and render evidence rows below each report section.

- [ ] **Step 4: Run frontend tests and build**

Run: `cd frontend; node --test src\researchReports.test.mjs`

Run: `cd frontend; npm run build`

Expected: PASS and build success.

### Task 3: Final Verification

**Files:**
- Modify: `智能竞品分析Agent_MVP开发待办清单.md`

- [ ] **Step 1: Update Stage 7.6 checklist text**

Mark chapter-level citation Evidence display complete.

- [ ] **Step 2: Run regression checks**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py -q`

Run: `cd frontend; node --test src\researchReports.test.mjs`

Run: `cd frontend; npm run build`

Expected: backend tests pass, helper tests pass, frontend build succeeds.
