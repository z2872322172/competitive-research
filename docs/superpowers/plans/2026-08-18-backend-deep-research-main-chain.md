# Backend Deep Research Main Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Advance the backend-only deep research workflow by making search planning an explicit LangGraph node.

**Architecture:** Keep the existing FastAPI and LangGraph workflow contract unchanged. Insert `build_search_plan` between `plan_research` and `discover_sources`, store a compact serializable plan in workflow state, and keep downstream discovery behavior compatible.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, LangGraph.

---

### Task 1: Explicit Search Planning Node

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/workflows/research_graph.py`

- [x] **Step 1: Write the failing test**

Update `test_stage_five_workflow_emits_node_lifecycle_events` and `test_stage_five_workflow_saves_success_checkpoints` so their expected workflow node sequence includes:

```python
"build_search_plan",
```

- [x] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py::test_stage_five_workflow_emits_node_lifecycle_events -q
```

Expected: fail because lifecycle events jump from `plan_research` directly to `discover_sources`.

- [x] **Step 3: Implement the minimal workflow node**

Add `build_search_plan` to `WORKFLOW_NODES`, `NODE_RESUME_TARGETS`, graph nodes, and graph edges. The node builds a serializable `search_plan` containing query, competitors, dimensions, source preferences, and budget, then returns `next_node="discover_sources"`.

- [x] **Step 4: Run the focused test to verify it passes**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py::test_stage_five_workflow_emits_node_lifecycle_events -q
```

Expected: pass with lifecycle events for `build_search_plan`.

- [x] **Step 5: Run backend regression tests**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest
```

Expected: all backend tests pass.

### Task 2: Search Plan Drives Discovery

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/workflows/research_graph.py`
- Modify: `backend/app/services/collection.py`

- [x] **Step 1: Write the failing workflow handoff test**

Add `test_stage_five_workflow_passes_search_plan_into_source_discovery` to verify the workflow passes the `search_plan` produced by `build_search_plan` into `discover_research_sources`.

- [x] **Step 2: Write the failing discovery behavior test**

Add `test_stage_five_discovery_uses_search_plan_query_and_manual_url_priority` to verify `discover_research_sources` uses the planned query and orders planned manual URLs before prompt URLs.

- [x] **Step 3: Run focused tests and verify they fail**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py::test_stage_five_workflow_passes_search_plan_into_source_discovery -q
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py::test_stage_five_discovery_uses_search_plan_query_and_manual_url_priority -q
```

Expected: fail because the workflow does not pass `search_plan`, and discovery does not accept the parameter.

- [x] **Step 4: Implement minimal search plan handoff**

Pass `search_plan` from workflow state into `research_service.discover_research_sources`. Add an optional `search_plan` parameter to `collection.discover_research_sources`, using `search_plan["query"]` when present and extracting manual URLs from `search_plan["source_preferences"]` before scanning the prompt.

- [x] **Step 5: Run focused and full backend tests**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py::test_stage_five_workflow_passes_search_plan_into_source_discovery -q
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py::test_stage_five_discovery_uses_search_plan_query_and_manual_url_priority -q
.\backend\.venv\Scripts\python.exe -m pytest
```

Expected: focused tests pass and the backend suite passes.

### Task 3: Search Plan Budget And Ordering

**Files:**
- Modify: `backend/tests/test_api_contract.py`
- Modify: `backend/app/workflows/research_graph.py`
- Modify: `backend/app/services/collection.py`

- [x] **Step 1: Write the failing budget and ordering test**

Add `test_stage_five_discovery_uses_search_plan_budget_and_source_priority` to verify the discovery adapter receives a capped `max_results`, then reorders and truncates returned candidates by planned source-type priority.

- [x] **Step 2: Run the focused test to verify it fails**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py::test_stage_five_discovery_uses_search_plan_budget_and_source_priority -q
```

Expected: fail because discovery still forwards the full configured search limit and does not trim or prioritize returned results.

- [x] **Step 3: Implement the minimal budget and ordering logic**

Use `search_plan["budget"]["max_candidate_sources"]` to cap adapter search results, apply `search_plan["source_type_priority"]` when sorting discovery candidates, and trim any adapter overage after sorting.

- [x] **Step 4: Run focused and full backend tests**

Run:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py::test_stage_five_discovery_uses_search_plan_budget_and_source_priority -q
.\backend\.venv\Scripts\python.exe -m pytest
```

Expected: focused test passes and backend suite passes.
