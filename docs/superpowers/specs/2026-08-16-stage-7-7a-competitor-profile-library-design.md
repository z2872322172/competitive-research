# Stage 7.7A Competitor Profile Library Design

## Goal

Make the competitor library a persisted product surface instead of a static frontend demo list.

## Scope

- Add a `CompetitorProfile` table owned by a lightweight `workspace_id`.
- Store common source URLs as structured JSON on each profile.
- Add APIs to create and list competitor profiles.
- Return aggregate counts for related tasks, verified claims, risky claims, and reports by matching competitor names in task scope and Claim subject.
- Switch the frontend competitor library page from static rows to API-backed rows.

## Backend Design

`CompetitorProfile` stores `workspace_id`, `name`, `category`, `description`, `homepage_url`, `source_urls_json`, timestamps, and a uniqueness constraint on `(workspace_id, name)`.

The first API slice uses a fixed default workspace (`default`) because full organization and user isolation belongs in a later 7.7B stage. The field exists now so future isolation does not require reshaping the table.

Endpoints:

- `POST /v1/competitors`
- `GET /v1/competitors`

List responses include aggregate stats:

- `task_count`: tasks whose scope competitors include this profile name.
- `verified_claim_count`: Claims with this subject and `status == verified`.
- `risky_claim_count`: Claims with this subject and risk statuses.
- `report_count`: reports attached to matched tasks.

## Frontend Design

The existing competitor library page keeps its dense operational layout. Rows come from `listCompetitors()` and show saved source count, verified/risky counts, report count, and latest update text. When no backend data is available, the page falls back to the existing demo rows.

## Testing

- Backend API contract test covers create, duplicate conflict, list response, source URL persistence, and aggregate stats after a research flow.
- Frontend helper test covers converting API competitor profiles into table rows and fallback behavior.
