# Stage 7.8A Task Recovery Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add clear frontend recovery feedback for failed, canceled, retryable, resumable, and cancelable tasks.

**Architecture:** Extend `frontend/src/researchTasks.js` with a pure helper and render its output in the task detail panel. Existing action buttons continue to call current retry/resume/cancel handlers.

**Tech Stack:** Vue 3, TypeScript, Node test runner.

---

### Task 1: Recovery Helper

**Files:**
- Modify: `frontend/src/researchTasks.js`
- Modify: `frontend/src/researchTasks.d.ts`
- Modify: `frontend/src/researchTasks.test.mjs`

- [ ] Add failing tests for `buildTaskRecoveryFeedback`.
- [ ] Implement helper with failed, canceled, active, completed cases.
- [ ] Run `node --test src\researchTasks.test.mjs`.

### Task 2: Task Detail UI

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/style.css`

- [ ] Add computed feedback for the active task.
- [ ] Render feedback in task detail panel.
- [ ] Run `npm run build`.

### Task 3: Checklist and Regression

**Files:**
- Modify: `智能竞品分析Agent_MVP开发待办清单.md`

- [ ] Mark Stage 7 recovery feedback验收项 complete.
- [ ] Run frontend task/review/report/competitor helper tests and build.
