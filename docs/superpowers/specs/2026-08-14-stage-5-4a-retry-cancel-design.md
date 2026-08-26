# Stage 5.4A Retry And Cancel Design

## Goal

Add the first usable failure-handling layer for the LangGraph research workflow: retry selected transient node failures and let users cancel a task before the workflow starts the next node.

## Scope

This increment keeps the current API loop and workflow shape intact. It does not introduce worker preemption, distributed cancellation, priority queues, or full Celery control; those belong to later Stage 5.4 / 5.6 work.

## Approach

Retry policy lives in `backend/app/workflows/research_graph.py` near node instrumentation because retry events and node lifecycle events must stay consistent. The first policy retries transient external-work nodes once: `discover_sources`, `fetch_sources`, `parse_sources`, `extract_evidence`, `extract_claims`, and `generate_report`. A retry writes `node.retrying` before the next attempt. If the final attempt fails, the workflow keeps the existing `node.failed` behavior and marks the run/task failed.

Cancellation is exposed through `POST /v1/research-tasks/{task_id}/cancel`. The service transitions cancelable tasks and the latest active run to `canceled`, records `run.canceled`, and stores a human-readable reason. Workflow nodes call a cancellation guard before starting work; if a task is canceled, the node writes `node.skipped` and raises an internal cancellation exception so later nodes do not run.

## Trade-Offs

- Retrying in node instrumentation is simple and keeps event ordering visible, but it is not yet a full per-provider retry strategy.
- Cancellation is cooperative at node boundaries. It will not interrupt a blocking HTTP request or LLM call mid-flight in inline mode.
- The API can cancel queued/running/waiting-review tasks; completed tasks remain immutable.

## Validation

Tests cover one retrying node that succeeds on the second attempt, the cancel API for a queued task, and a workflow run that stops before a node when cancellation is already requested.

