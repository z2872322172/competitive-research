# Stage 5 Baseline Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the Stage 5.0 cleanup item by adding a safe, documented way to inventory and optionally remove local development artifacts.

**Architecture:** Add a small Python utility under `backend/scripts/` that can scan known local artifact paths from the project root. The utility defaults to dry-run and only deletes files/directories when called with `--apply`, keeping cleanup explicit and testable.

**Tech Stack:** Python standard library, pytest, Markdown documentation.

---

### Task 1: Cleanup Utility Contract

**Files:**
- Create: `backend/tests/test_dev_cleanup.py`
- Create: `backend/scripts/cleanup_dev_artifacts.py`

- [x] **Step 1: Write the failing dry-run test**

Create `backend/tests/test_dev_cleanup.py` with tests that import `collect_artifacts` and `cleanup_artifacts`, create temporary artifact files, and assert dry-run reports them without deleting them.

- [x] **Step 2: Run the targeted test to verify RED**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_dev_cleanup.py -q`

Expected: fail because `backend.scripts.cleanup_dev_artifacts` does not exist.

- [x] **Step 3: Implement the minimal utility**

Create `backend/scripts/cleanup_dev_artifacts.py` with:
- `DEFAULT_ARTIFACT_PATTERNS`
- `collect_artifacts(root: Path) -> list[Artifact]`
- `cleanup_artifacts(root: Path, apply: bool = False) -> CleanupResult`
- CLI flags `--root` and `--apply`

- [x] **Step 4: Run the targeted test to verify GREEN**

Run: `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_dev_cleanup.py -q`

Expected: pass.

### Task 2: Ignore Policy and Documentation

**Files:**
- Create: `.gitignore`
- Modify: `README.md`
- Modify: `智能竞品分析Agent_MVP开发待办清单.md`

- [x] **Step 1: Add root ignore policy**

Add a root `.gitignore` covering local databases, logs, caches, Python bytecode, virtualenvs, `node_modules`, and frontend build output.

- [x] **Step 2: Document cleanup workflow**

Update `README.md` with dry-run and apply examples for `backend/scripts/cleanup_dev_artifacts.py`.

- [x] **Step 3: Update the MVP checklist**

Mark the Stage 5.0 cleanup item complete and mention the non-destructive artifact inventory.

### Task 3: Final Verification

**Files:**
- No code changes.

- [x] **Step 1: Run backend tests**

Run: `backend\.venv\Scripts\python.exe -m pytest`

Expected: all tests pass.

- [x] **Step 2: Run frontend build**

Run: `npm run build` from `frontend`.

Expected: build completes successfully.
