# Stage 5.4C Schema Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add failed checkpoint summaries and prove LLM schema failures can be recovered through workflow resume.

**Architecture:** Persist failed checkpoints in `backend/app/workflows/research_graph.py` while keeping resume based on the latest successful checkpoint. Change LLM claim extraction fallback semantics only for schema/validation failures.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, LangGraph workflow wrapper.

---

### Task 1: Failed Checkpoint Summary

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/workflows/research_graph.py`

- [x] Add a pytest that forces `fetch_sources` to fail and asserts a failed `WorkflowCheckpoint` is written.
- [x] Run the single test and verify it fails because failed checkpoints are not saved.
- [x] Implement `save_failed_checkpoint`.
- [x] Run the single test and verify it passes.

### Task 2: LLM Schema Failure Recovery

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/services/analysis/claim_extractor.py`
- Modify: `backend/app/workflows/research_graph.py`

- [x] Add a pytest where `extract_and_store_claims` first raises `ValueError("schema_validation_failed:...")`, then succeeds after `resume=True`.
- [x] Run the single test and verify it fails because schema failures are not persisted as failed checkpoints.
- [x] Ensure schema failures are non-retryable and persist failed checkpoint metadata.
- [x] Run the single test and verify it passes.

### Task 3: Documentation And Verification

**Files:**
- Modify: `智能竞品分析Agent_MVP开发待办清单.md`

- [x] Update Stage 5.4 checklist and 5.4C note.
- [ ] Run `backend\.venv\Scripts\python.exe -m pytest`.
- [ ] Run `npm run build` from `frontend`.
