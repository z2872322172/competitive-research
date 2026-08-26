# Stage 7.3 Resume Failed Node Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a user-facing action that resumes a failed research run from its latest successful workflow checkpoint.

**Architecture:** Reuse the existing `WorkflowCheckpoint` and `run_research_workflow(..., resume=True)` path. Add a narrow service guard that only queues failed runs with a success checkpoint, then expose it through a `/resume` API and frontend button.

**Tech Stack:** FastAPI, SQLAlchemy, LangGraph workflow, Celery task wrapper, Vue 3, TypeScript, Node test runner, pytest.

---

### Task 1: Backend Resume API

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/services/research_service.py`
- Modify: `backend/app/api/routes.py`
- Modify: `backend/app/workers/tasks.py`

- [ ] **Step 1: Write the failing API test**

Add a test that creates a failed run with a successful checkpoint, calls `POST /v1/research-tasks/{task_id}/resume`, and asserts the same run reaches `waiting_review`.

- [ ] **Step 2: Run test to verify it fails**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py::test_stage_seven_failed_task_can_resume_from_checkpoint_api -q`

Expected: FAIL with 404 or missing endpoint behavior.

- [ ] **Step 3: Implement minimal backend support**

Add `prepare_failed_run_resume`, route `/research-tasks/{task_id}/resume`, and allow the Celery task to pass `resume=True`.

- [ ] **Step 4: Run targeted backend test**

Run the same pytest command.

Expected: PASS.

### Task 2: Frontend Resume Action

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.vue`

- [ ] **Step 1: Add API wrapper**

Add `resumeResearchTask(taskId)` that posts to `/research-tasks/{taskId}/resume`.

- [ ] **Step 2: Add UI action**

Show “继续执行” on failed current tasks and failed timeline nodes. Call the resume API, reload task detail, start polling when the task is queued/running, and keep the existing “重试” action as full rerun.

- [ ] **Step 3: Build frontend**

Run: `npm run build` in `frontend`.

Expected: PASS.

### Task 3: Todo Update And Verification

**Files:**
- Modify: `智能竞品分析Agent_MVP开发待办清单.md`

- [ ] **Step 1: Mark 7.3 resume entry complete**

Change `支持从失败节点继续执行的操作入口` from unchecked to checked and add a concise MVP note.

- [ ] **Step 2: Run backend contract suite**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py -q`

Expected: PASS.
