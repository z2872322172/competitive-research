# Stage 7.5B Batch Accept Low-Risk Claims Design

## Goal

Add a review-page action that accepts clearly low-risk claims in bulk, so reviewers can focus manual effort on conflict, undisclosed, low-confidence, and missing-evidence claims.

## Scope

This stage is frontend-only. It reuses the existing `POST /v1/claims/{claim_id}/review` API by submitting one `accept` review per low-risk claim. No backend endpoint or schema change is required.

## Low-Risk Rule

A claim is eligible for batch acceptance when all of these are true:

- `include_in_report` is `true`.
- `review_decision` is empty or `continue_research`.
- `status` is `verified`.
- `confidence_score >= 0.8`.
- `evidence_coverage >= 0.8`.
- At least one evidence id is bound.

Risky statuses (`conflict`, `undisclosed`, `low_confidence`, `needs_evidence`) remain excluded from the bulk action.

## Frontend Behavior

The review page shows a compact bulk action above the review list. The action displays the number of eligible claims and is disabled when there is no active task, a request is already loading, or no claims qualify.

When clicked, the page submits each eligible claim through the existing `reviewClaim` client with decision `accept` and a consistent reason: `批量接受：低风险 Claim 已达到置信度和引用覆盖率阈值。`

After the batch completes, the page reloads the current task detail and task list. If one request fails, the existing page-level error state shows the failure and the reviewer can retry.

## Testing

Add helper tests for candidate selection:

- Includes only verified, included, unreviewed claims with enough confidence, coverage, and evidence.
- Excludes risky statuses, excluded-from-report claims, accepted claims, and low-quality claims.

Existing build and helper tests remain the verification surface for this frontend-only change.
