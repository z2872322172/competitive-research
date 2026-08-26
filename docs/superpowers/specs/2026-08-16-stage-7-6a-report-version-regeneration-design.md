# Stage 7.6A Report Version Regeneration Design

## Goal

Make report versions visible and controllable after claim review. Reviewers should be able to see report history and explicitly regenerate a new report version from the current reviewed Claim state.

## Scope

This stage productizes existing backend capabilities. The data model already supports `Report.version`, and review completion can already create a new version. Stage 7.6A adds a clear API and frontend controls around that capability.

Out of scope:

- PDF export.
- DOCX export.
- Major report template redesign.
- Long-running async report regeneration.

## Backend Behavior

Add `POST /v1/research-tasks/{task_id}/reports/regenerate`.

The endpoint:

- Requires the task to exist.
- Requires at least one existing report.
- Requires no unresolved risky Claim, where risky statuses are `conflict`, `undisclosed`, `low_confidence`, and `needs_evidence`, unless the latest review decision is neither empty nor `continue_research`.
- Reuses the latest task run for event traceability.
- Creates a new report with `version = latest_version + 1`.
- Uses generation reason `manual_regenerate`.
- Returns the new `ReportOut`.

If unresolved risky Claims remain, return HTTP 409 with a clear error message.

## Frontend Behavior

The report page keeps the existing version history list and improves it into a version switcher with:

- Version number.
- Generation reason label from `input_snapshot.report_generation.reason`.
- Generated time.
- Citation coverage.

Add a compact `重新生成` button on the report page. The button calls the new backend endpoint, reloads task detail, and selects the newly created version.

## Testing

Backend contract tests cover:

- Regeneration creates the next report version and returns `generation_reason = manual_regenerate`.
- Regeneration is blocked with HTTP 409 while risky Claims are unresolved.

Frontend helper tests cover:

- Building version history view models from `ReportOut[]`.
- Selecting the latest regenerated report after API success.
