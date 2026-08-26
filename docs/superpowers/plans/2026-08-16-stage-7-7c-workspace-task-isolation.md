# Stage 7.7C Workspace Task Isolation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal workspace/user boundary to research task creation and listing.

**Architecture:** Add a `workspace_id` column to `ResearchTask`, expose it through Pydantic schemas, persist it in `create_task()`, and filter task list queries by `workspace_id` and `created_by`.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, Vue TypeScript types.

---

### Task 1: Backend Workspace Filtering

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/models.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/services/research_service.py`
- Modify: `backend/app/api/routes.py`
- Modify: `backend/app/db.py`

- [ ] Write failing API contract test for workspace and created_by task filtering.
- [ ] Run focused pytest and confirm RED.
- [ ] Add `workspace_id` to model/schema/service/db upgrade.
- [ ] Add route query filters.
- [ ] Run focused pytest and confirm GREEN.

### Task 2: Frontend Types

**Files:**
- Modify: `frontend/src/api.ts`

- [ ] Add optional `workspace_id` and `created_by` to `ResearchTaskCreate`.
- [ ] Add `workspace_id` to `ResearchTaskOut`.
- [ ] Add optional `workspace_id` and `created_by` to `listResearchTasks()` params.
- [ ] Run frontend build.

### Task 3: Checklist and Regression

**Files:**
- Modify: `智能竞品分析Agent_MVP开发待办清单.md`

- [ ] Mark Stage 7.7 workspace concept partially complete.
- [ ] Run backend API contract suite.
- [ ] Run frontend helper tests and build.
