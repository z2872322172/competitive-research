# Stage 7.6C PDF / DOCX Export Design

## Goal

Extend the existing report export flow so users can download the current report as Markdown, PDF, or DOCX from the report page.

## Scope

This stage builds on the existing `ReportOut` model, report version history, and Markdown export endpoint.

Out of scope:

- Redesigning report content.
- Async export jobs.
- Archive packaging or email delivery.

## Backend Behavior

Keep the existing `POST /v1/reports/{report_id}/export?format=markdown` entry point and add support for:

- `format=pdf`
- `format=docx`

Add a shared renderer that converts a `ReportOut` into export payloads using the current version's sections and section evidence.

Rendering rules:

- Preserve report title, version, and citation coverage.
- Render sections in order.
- Render section evidence under each section.
- Preserve plain Markdown export behavior.
- Return binary responses for PDF and DOCX with stable filenames.

Implementation choice:

- Use `reportlab` for PDF generation.
- Use `python-docx` for DOCX generation.

## Frontend Behavior

Keep the current report page as the export entry point.

Add compact export actions for:

- Markdown
- PDF
- DOCX

Each action should download the currently selected report version and keep the existing version switcher behavior unchanged.

## Testing

Backend tests should cover:

- Markdown export remains unchanged.
- PDF export returns a PDF response with non-empty bytes.
- DOCX export returns a DOCX response with non-empty bytes.
- Unknown export formats return a clear 400 error.

Frontend tests should cover:

- Export requests pass the selected format through.
- The selected report version is used for download.
