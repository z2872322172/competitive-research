# Stage 7.5A Claim Review Context Design

## Goal

Make the Claim review page useful enough for real decisions by showing each risky Claim's quality context and letting reviewers enter a reason before submitting a review decision.

## Scope

This stage improves the existing frontend review workflow only. It reuses the current `POST /v1/claims/{claim_id}/review` backend API and does not add bulk review, new report generation controls, or backend schema changes.

## Frontend Design

Add a small `researchReview` helper module that converts backend `ClaimOut` records and Evidence view models into `ReviewItem` objects. Each review item exposes the Claim id, display text, risk kind, confidence score, evidence coverage, status label, bound Evidence summaries, and a default recommendation. The Vue page can render these fields without embedding mapping rules in the template.

The review page keeps the four existing actions: accept, mark uncertain, exclude, and continue research. Each card gets a textarea keyed by `claimId`. When the user submits a decision, the handler sends the typed reason if present; otherwise it sends the recommendation as a fallback.

Bound Evidence is shown as compact buttons with Evidence id, source type, confidence, and title. Clicking a button reuses the existing Evidence detail selection.

## Testing

Add Node tests for the helper module:

- Risky Claim filtering excludes already processed Claims except `continue_research`.
- Review items include confidence, evidence coverage, status labels, and bound Evidence summaries.
- Review reason resolution prefers typed input and falls back to the recommendation.

The final verification runs the new frontend helper tests, existing Evidence helper tests, backend API contract tests, and `npm run build`.

## Out Of Scope

Bulk accept, backend validation changes, report regeneration controls, and report version UI remain for later 7.5/7.6 slices.
