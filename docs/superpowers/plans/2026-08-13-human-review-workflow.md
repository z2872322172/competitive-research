# Human Review Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the MVP human-review workflow so risky claims can be reviewed, tasks can move to completed, and "continue research" remains an explicit follow-up path.

**Architecture:** Reuse the existing FastAPI review endpoint, SQLAlchemy review_decisions table, Vue task detail state, and report view. Backend changes focus on review status semantics and event traceability. Frontend changes focus on making each review action visible, refreshing task state, and routing users to report or rerun as appropriate.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, Vue 3, TypeScript, Vite.

---

### Task 1: Backend Review Completion Contract

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/api/routes.py`
- Modify: `backend/app/services/research_service.py`

- [ ] Add a pytest covering full review completion and continue-research behavior.
- [ ] Run only that test and confirm it fails before production edits.
- [ ] Preserve existing review endpoint shape while recording useful review events.
- [ ] Ensure all risky claims must have a non-continue latest review before task completion.
- [ ] Run the targeted test and then the backend test suite.

### Task 2: Frontend Review UX

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/api.ts` if response typing is needed
- Modify: `frontend/src/style.css`

- [ ] Add explicit review action labels for accept, mark uncertain, exclude, and continue research.
- [ ] Refresh the task after each action and show a concise success message.
- [ ] Hide handled review items while keeping metrics updated.
- [ ] Expose a rerun action when a claim is marked continue_research.
- [ ] Run the frontend build.

### Task 3: Documentation Status

**Files:**
- Modify: `智能竞品分析Agent_MVP开发待办清单.md`
- Modify: `README.md` if current capabilities need a status adjustment

- [ ] Update the current execution order to mark the review workflow as implemented.
- [ ] Keep LangGraph and infrastructure as the next open work.
- [ ] Run backend tests and frontend build before final response.
