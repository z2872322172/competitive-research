# Stage 5.4B Failure Classification Design

## Goal

Make workflow failures more precise by distinguishing retryable transient errors from non-retryable workflow/data errors, persisting retry counts in checkpoints, and preserving report failure observability.

## Scope

This increment refines the Stage 5.4A retry wrapper. It does not add distributed retry queues, exponential backoff, worker preemption, or frontend controls.

## Approach

The workflow wrapper classifies errors before retrying. Transient `RuntimeError` messages containing `temporary`, `transient`, `timeout`, or `rate limit` remain retryable. Structural errors such as missing workflow state, invalid task/run IDs, schema validation failures, and final report generation failures are non-retryable.

When a node succeeds after retry, the success checkpoint stores `retry_count` and includes it in the checkpoint state summary. This makes resume diagnostics visible without changing the public task detail API.

Report generation keeps the existing `report.generate_failed` events from `generate_report_with_retry`. When report generation exhausts its internal attempts, the workflow wrapper records `node.failed` for `generate_report` and marks the run recoverable from the previous checkpoint.

## Validation

Tests cover non-retryable failures not emitting `node.retrying`, retry count persistence on a successful retry, and final report failure emitting both `report.generate_failed` and `node.failed`.

