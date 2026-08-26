# Stage 7.4 Evidence Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users inspect Evidence metadata and filter task Evidence by competitor, dimension, and source type without changing the existing task detail contract.

**Architecture:** Add optional Evidence filter query parameters to the task detail endpoint and apply them only to the Evidence collection. The frontend keeps the existing research workspace layout, adds compact filter controls to the Evidence panel, and sends the active filters when refreshing task detail.

**Tech Stack:** FastAPI, SQLAlchemy, Vue 3, TypeScript, Vite, Node test runner, pytest.

---

### Task 1: Backend Evidence Filter Contract

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/api/routes.py`
- Modify: `backend/app/services/research_service.py`

- [x] **Step 1: Write the failing contract test**

Add `test_stage_seven_task_detail_filters_evidence_by_source_competitor_and_dimension` to verify:
- `evidence_source_type=official` returns only official-source Evidence.
- `evidence_competitor=Cursor` returns Evidence linked to Cursor claims.
- `evidence_dimension=pricing` returns Evidence linked to pricing claims.

- [x] **Step 2: Run the targeted test and confirm RED**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py::test_stage_seven_task_detail_filters_evidence_by_source_competitor_and_dimension -q
```

Expected: fails because the endpoint ignores the new query parameters.

- [x] **Step 3: Implement the endpoint and service filter**

Add optional `evidence_competitor`, `evidence_dimension`, and `evidence_source_type` parameters to `GET /v1/research-tasks/{task_id}`. Filter Evidence through `Source.source_type` and `ClaimEvidence -> Claim` joins, with dimension matching both `Claim.dimension` and `Claim.claim_type`.

- [x] **Step 4: Run the targeted test and confirm GREEN**

Run the same pytest command. Expected: pass.

### Task 2: Frontend Evidence Filter Controls

**Files:**
- Modify: `frontend/src/researchEvidence.js`
- Modify: `frontend/src/researchEvidence.d.ts`
- Modify: `frontend/src/researchEvidence.test.mjs`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [x] **Step 1: Write failing pure-function tests**

Add tests for `buildEvidenceQuery` and `filterEvidenceViewModels`.

- [x] **Step 2: Implement filter helpers**

Expose query serialization, fallback source-type filtering, raw `sourceType`, and `extractionMethod` on the Evidence view model.

- [x] **Step 3: Wire API and UI**

Allow `getResearchTask(taskId, evidenceQuery)` and add source type, competitor, and dimension selects to the Evidence panel. Keep old calls compatible by defaulting the query to empty.

- [x] **Step 4: Show extraction method in Evidence detail surfaces**

Render `extractionMethod` in the run-page floating Evidence detail and report citation drawer alongside locator and quality score.

- [x] **Step 5: Verify frontend**

Run:

```powershell
node --test src\researchEvidence.test.mjs
npm run build
```

Expected: tests and build pass.
