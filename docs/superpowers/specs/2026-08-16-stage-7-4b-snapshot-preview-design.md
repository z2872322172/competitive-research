# Stage 7.4B Snapshot Preview Design

## Goal

Evidence detail views should let users inspect the captured HTML snapshot or a readable snapshot summary for the Evidence source.

## Scope

This stage adds a small source snapshot read contract and wires it into the existing Evidence detail surfaces. It does not add full HTML rendering, object storage, or snapshot editing.

## Backend Design

Add `GET /v1/sources/{source_id}/snapshot`. The endpoint looks up the source, finds its `html_snapshot` artifact, and reads the file from `artifact_storage_dir`. A successful response includes `source_id`, `artifact_type`, `available`, `content_hash`, `object_key`, `summary`, and `char_count`.

If the source is missing, return 404. If the artifact row or file is missing, return a normal 200 response with `available=false` and an empty summary so the UI can show a stable unavailable state.

The service should keep path resolution inside `artifact_storage_dir` and reject object keys that escape that directory.

## Frontend Design

Add `getSourceSnapshot(sourceId)` to `frontend/src/api.ts`. Extend the Evidence view model with `sourceId` so existing cards can request the snapshot for the selected source.

In the running-workspace floating Evidence panel and report citation drawer, replace the static snapshot hint with a compact button. On click, fetch the snapshot and show a small text preview, missing-state copy, or an error state. Existing “打开来源” behavior remains unchanged.

## Testing

Backend API contract tests cover available snapshot, missing artifact/file fallback, and missing source. Frontend tests cover snapshot response normalization and Evidence view models carrying `sourceId`. Full verification runs backend pytest, frontend node tests, and frontend build.

## Out Of Scope

Full HTML iframe rendering, MinIO/S3 support, PDF/DOCX export, and Claim review changes stay for later stages.
