# Stage 5.4B Failure Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refine workflow failure handling with exception classification, checkpoint retry counts, and report failure node events.

**Architecture:** Keep all workflow retry classification in `backend/app/workflows/research_graph.py`. Use existing `WorkflowCheckpoint.retry_count`, `node.retrying`, `node.failed`, and `report.generate_failed` events.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, LangGraph workflow wrapper.

---

### Task 1: Exception Classification

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/workflows/research_graph.py`

- [x] Add a pytest where `fetch_research_sources` raises `ValueError("source_discovery_missing")`.
- [x] Run the single test and verify it fails because the node retries.
- [x] Add `is_retryable_workflow_error`.
- [x] Run the single test and verify it passes.

### Task 2: Checkpoint Retry Counts

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/workflows/research_graph.py`

- [x] Extend the successful retry test to assert the `fetch_sources` checkpoint has `retry_count == 1`.
- [x] Run the single test and verify it fails because retry count is not saved.
- [x] Pass retry count into `save_success_checkpoint`.
- [x] Run the single test and verify it passes.

### Task 3: Final Report Failure Observability

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/workflows/research_graph.py`

- [x] Add a pytest where report generation fails through all internal attempts.
- [x] Run the single test and verify it fails because workflow retry semantics are too broad.
- [x] Keep `report_generation_failed` non-retryable and let the wrapper emit `node.failed`.
- [x] Run the single test and verify it passes.

### Task 4: Documentation And Verification

**Files:**
- Modify: `智能竞品分析Agent_MVP开发待办清单.md`

- [x] Update Stage 5.4 checklist and 5.4B note.
- [x] Run `backend\.venv\Scripts\python.exe -m pytest`.
- [x] Run `npm run build` from `frontend`.
