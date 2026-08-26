# Stage 7.7C Workspace Task Isolation Design

## Goal

Research tasks should carry a workspace boundary and support filtered list queries, matching the competitor profile workspace model introduced in Stage 7.7A.

## Scope

- Add `workspace_id` to `ResearchTask`.
- Accept `workspace_id` and `created_by` in task creation payloads.
- Return `workspace_id` in `ResearchTaskOut`.
- Support `GET /v1/research-tasks?workspace_id=...&created_by=...`.
- Keep default behavior compatible with existing clients by using `workspace_id = "default"` and `created_by = "local-user"`.

## Non-Goals

- No authentication or authorization enforcement yet.
- No organization membership model yet.
- No frontend workspace switcher yet.

## Testing

API contract tests cover creating tasks in two workspaces and listing by workspace and user.
