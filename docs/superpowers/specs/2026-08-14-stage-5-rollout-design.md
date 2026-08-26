# Stage 5 Rollout Design

## Goal

Open the remaining Stage 5 capabilities in small, testable increments while preserving the current MVP demo loop.

## Scope

The rollout starts with development-environment reproducibility, then moves into workflow checkpoint and recovery. Infrastructure, product polish, and deployment work stay behind the workflow stability work.

## Sequence

1. Finish Stage 5.0 baseline cleanup with a non-destructive artifact inventory and documented cleanup workflow.
2. Implement Stage 5.3 checkpoint and resume so workflow nodes can be restored from the latest successful checkpoint.
3. Add Stage 5.4 node retry, failure handling, and cancellation.
4. Add Stage 5.5 post-review report regeneration with version history.
5. Add Stage 5.6 real Celery async execution once recovery semantics are stable.

## First Increment Design

The first increment adds a small development artifact inventory utility. It identifies local-only files such as SQLite databases, logs, caches, and build output, and supports an explicit apply mode for deletion. The default mode is dry-run so it is safe to run during normal development.

The repository currently has separate backend and frontend ignore files but no root ignore policy. The first increment adds a root `.gitignore` for known local artifacts and a short README section documenting the cleanup command. This gives Stage 5.3 a cleaner baseline without touching runtime behavior.

## Validation

The cleanup utility gets pytest coverage for dry-run inventory and explicit apply mode. Existing backend tests and frontend build remain the final baseline check.

