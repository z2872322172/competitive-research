# Stage 5.4C Schema Recovery Design

## Goal

Make LLM schema-repair failures observable and recoverable instead of silently falling back to rule-based extraction.

## Scope

This increment focuses on `extract_claims` failures. It does not add new UI controls or change report regeneration.

## Approach

LLM extraction still falls back for unavailable providers and transient LLM runtime failures. Schema/validation failures become non-retryable workflow failures by propagating an error marker such as `schema_validation_failed`. The workflow wrapper already classifies this as non-retryable.

When a node finally fails, the workflow saves a failed checkpoint containing the node name, input summary, error summary, retry count, and a state snapshot. Resume still starts from the latest successful checkpoint, so the user can fix the underlying issue and continue from the previous good node.

## Validation

Tests cover:

- Failed nodes persist a failed checkpoint with `error_summary`.
- An LLM schema failure in `extract_claims` writes `node.failed`, stores a failed checkpoint, keeps the latest successful checkpoint as the resume source, and can complete after the extractor is fixed and `resume=True` is used.

