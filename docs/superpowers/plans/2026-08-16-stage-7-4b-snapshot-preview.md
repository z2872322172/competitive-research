# Stage 7.4B Snapshot Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users inspect a source HTML snapshot summary from Evidence detail views.

**Architecture:** Add a backend read service and API endpoint for source snapshot artifacts, returning a stable unavailable response when the snapshot cannot be read. The frontend adds a typed API wrapper and fetches snapshot summaries on demand from existing Evidence detail panels.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, Vue 3, TypeScript, Node test runner, pytest.

---

### Task 1: Backend Snapshot Contract

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/services/research_service.py`
- Modify: `backend/app/api/routes.py`
- Modify: `backend/tests/test_api_contract.py`

- [x] **Step 1: Write failing API contract tests**

Add tests that create a source with an `html_snapshot` artifact, write the matching local HTML file under the configured artifact directory, and assert `GET /v1/sources/{source_id}/snapshot` returns `available=true` with a readable summary. Add tests for a source without a readable snapshot returning `available=false`, and an unknown source returning 404.

- [x] **Step 2: Run targeted backend tests and confirm RED**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py -q
```

Expected: snapshot tests fail because the endpoint and schema do not exist.

- [x] **Step 3: Implement snapshot schema, service, and route**

Create `SourceSnapshotOut` in `backend/app/schemas.py`. Add `get_source_snapshot(db, source_id)` to `backend/app/services/research_service.py` and `GET /v1/sources/{source_id}/snapshot` in `backend/app/api/routes.py`. The service must resolve artifact paths relative to `get_settings().artifact_storage_dir` and return unavailable output instead of raising when the artifact row or file is missing.

- [x] **Step 4: Run targeted backend tests and confirm GREEN**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py -q
```

Expected: all API contract tests pass.

### Task 2: Frontend Snapshot View Model and API

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/researchEvidence.js`
- Modify: `frontend/src/researchEvidence.d.ts`
- Modify: `frontend/src/researchEvidence.test.mjs`

- [x] **Step 1: Write failing frontend tests**

Add tests that verify `buildEvidenceViewModel` keeps the raw `source_id` as `sourceId` and that snapshot labels prefer available summaries over static hints.

- [x] **Step 2: Run targeted frontend tests and confirm RED**

Run:

```powershell
cd frontend
node --test src\researchEvidence.test.mjs
```

Expected: tests fail because `sourceId` and snapshot formatting helpers are missing.

- [x] **Step 3: Implement API types and Evidence helpers**

Add `SourceSnapshotOut` and `getSourceSnapshot(sourceId)` to `frontend/src/api.ts`. Add Evidence helper exports for stable snapshot display text and add `sourceId` to the Evidence view model.

- [x] **Step 4: Run targeted frontend tests and confirm GREEN**

Run:

```powershell
cd frontend
node --test src\researchEvidence.test.mjs
```

Expected: Evidence helper tests pass.

### Task 3: Frontend Evidence Detail Integration

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [x] **Step 1: Wire snapshot loading state**

Import `getSourceSnapshot`, store snapshot responses by `sourceId`, and expose `loadEvidenceSnapshot(evidence)` for the floating Evidence panel and citation drawer.

- [x] **Step 2: Render snapshot summary controls**

Replace static snapshot hint text with a compact button and a summary block. The UI should show loading, available summary, unavailable state, and error state without changing the surrounding layout.

- [x] **Step 3: Run final verification**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py -q
cd frontend
node --test src\researchEvidence.test.mjs
npm run build
```

Expected: backend API tests, frontend helper tests, and production build pass.
