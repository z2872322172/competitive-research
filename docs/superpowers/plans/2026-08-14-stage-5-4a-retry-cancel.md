# Stage 5.4A Retry And Cancel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-pass workflow node retry events and cooperative task cancellation.

**Architecture:** Keep retry/cancel behavior inside the workflow and research service boundaries already in use. Add a cancellation API route that calls service code, and keep frontend work out of this increment unless type wiring is needed later.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, LangGraph workflow wrapper.

---

### Task 1: Node Retry Behavior

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/workflows/research_graph.py`

- [x] Add a pytest where `research_service.fetch_research_sources` fails once, then succeeds.
- [x] Run that single test and verify it fails because no retry occurs.
- [x] Add a small retry policy and emit `node.retrying` before the second attempt.
- [x] Run the single test and verify it passes.

### Task 2: Cancellation API

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/services/research_service.py`
- Modify: `backend/app/api/routes.py`

- [x] Add a pytest that creates a queued run and calls `POST /v1/research-tasks/{task_id}/cancel`.
- [x] Run that single test and verify it fails because the route does not exist.
- [x] Implement `cancel_research_task` service behavior and API route.
- [x] Run the single test and verify it passes.

### Task 3: Workflow Cancellation Guard

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/workflows/research_graph.py`

- [x] Add a pytest where a task/run is canceled before `run_research_workflow` starts.
- [x] Run that single test and verify it fails because workflow still runs.
- [x] Add a node-boundary cancellation guard that writes `node.skipped` and stops execution.
- [x] Run the single test and verify it passes.

### Task 4: Documentation And Verification

**Files:**
- Modify: `智能竞品分析Agent_MVP开发待办清单.md`

- [x] Mark the completed Stage 5.4A items and leave worker preemption for later.
- [x] Run `backend\.venv\Scripts\python.exe -m pytest`.
- [x] Run `npm run build` from `frontend`.
