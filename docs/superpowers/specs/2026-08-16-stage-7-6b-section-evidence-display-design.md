# Stage 7.6B Section Evidence Display Design

## Goal

Report readers can inspect the Evidence attached to each report section without leaving the report page. The API returns section-level evidence snapshots, and the frontend renders those snapshots below the matching section content.

## Scope

- Add a structured `evidence` array to each `ReportSectionOut`.
- Persist section-to-evidence references inside the report input snapshot at generation time.
- Render compact Evidence rows under report sections in the report page.
- Keep older reports compatible by returning an empty `evidence` array when no section evidence snapshot exists.

## Backend Design

Report generation already loads included Claims and their Evidence links. Stage 7.6B extends that structured data into `input_snapshot.report_generation.section_evidence`.

The section mapping is intentionally conservative:

- `executive_summary`, `key_claims`, `citation_coverage`, and `comparison` use all included claim Evidence.
- `review_risks` uses Evidence from included risky Claims.
- `collection_summary` has no Claim Evidence because it summarizes collection metrics.

Each section Evidence item stores a versioned snapshot with `id`, `source_id`, `quote`, `source_title`, `source_url`, `publisher`, `quality_score`, `relation`, and `claim_ids`. The snapshot keeps historical report versions stable even if Source or Evidence records change later.

## Frontend Design

The report document keeps section markdown as the primary content. Under a section with Evidence, the UI shows a compact list containing the Evidence id, source title, quality percentage, and quote. A helper in `researchReports.js` prepares display rows so Vue markup stays thin and testable.

## Compatibility

No database migration is required. Existing reports that lack `section_evidence` serialize with `evidence: []`.

## Testing

- Backend API contract test verifies report sections include section-level Evidence snapshots after a demo research flow.
- Frontend helper test verifies Evidence rows are normalized, sorted, labeled, and safe when missing.
