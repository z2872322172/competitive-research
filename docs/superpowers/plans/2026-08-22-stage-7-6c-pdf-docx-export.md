# Stage 7.6C PDF / DOCX Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users export the current report as Markdown, PDF, or DOCX from the report page without changing report version behavior.

**Architecture:** Add a shared backend report-export renderer that turns `ReportOut` into markdown text or binary PDF/DOCX output. Keep the existing export endpoint and extend it by format. On the frontend, keep the existing report page as the export entry point and add compact actions for the three formats.

**Tech Stack:** FastAPI, SQLAlchemy, `reportlab`, `python-docx`, Vue 3, Vite, Node test runner.

---

### Task 1: Backend export renderer and API

**Files:**
- Create: `backend/app/services/report_export.py`
- Modify: `backend/app/api/routes.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/tests/test_api_contract.py`

- [ ] **Step 1: Write the failing test**

Add a contract test that hits:

```python
markdown = client.post(f"/v1/reports/{report_id}/export?format=markdown")
pdf = client.post(f"/v1/reports/{report_id}/export?format=pdf")
docx = client.post(f"/v1/reports/{report_id}/export?format=docx")
unknown = client.post(f"/v1/reports/{report_id}/export?format=txt")

assert markdown.status_code == 200
assert markdown.json()["content"].startswith("## ")
assert pdf.status_code == 200
assert pdf.headers["content-type"].startswith("application/pdf")
assert len(pdf.content) > 100
assert docx.status_code == 200
assert docx.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
assert len(docx.content) > 100
assert unknown.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py -k report_export -v
```

Expected: fail because `pdf` and `docx` formats are not implemented yet.

- [ ] **Step 3: Write minimal implementation**

Implement `render_report_export(report, format)` with three branches:

```python
def render_report_export(report: ReportOut, format: str) -> tuple[bytes, str, str]:
    if format == "markdown":
        return markdown_json_bytes, "application/json", f"{slug}.json"
    if format == "pdf":
        return pdf_bytes, "application/pdf", f"{slug}.pdf"
    if format == "docx":
        return docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", f"{slug}.docx"
    raise ValueError("unsupported_export_format")
```

Use `reportlab` for PDF and `python-docx` for DOCX. Keep section order and render section evidence under each section.

Route the existing endpoint through the helper and set `Content-Disposition` for binary downloads.

Keep the existing Markdown JSON response shape unchanged.

Add the two packages to `backend/requirements.txt`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_api_contract.py -k report_export -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/report_export.py backend/app/api/routes.py backend/requirements.txt backend/tests/test_api_contract.py
git commit -m "feat: add pdf and docx report export"
```

### Task 2: Frontend export actions

**Files:**
- Create: `frontend/src/researchExport.js`
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/researchReports.test.mjs`

- [ ] **Step 1: Write the failing test**

Add a helper test for export labels and filenames:

```js
assert.equal(buildReportExportDescriptor('pdf').extension, 'pdf')
assert.equal(buildReportExportDescriptor('docx').mimeType, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
assert.equal(buildReportExportFilename('Trae 竞品分析', 'pdf'), 'Trae 竞品分析.pdf')
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
node --test frontend\src\researchReports.test.mjs
```

Expected: fail because export descriptor helpers do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add a small export helper module and use it from the report page:

```js
export function buildReportExportDescriptor(format) {
  const table = {
    markdown: { extension: 'md', mimeType: 'text/markdown' },
    pdf: { extension: 'pdf', mimeType: 'application/pdf' },
    docx: { extension: 'docx', mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' },
  }
  return table[format] || table.markdown
}
```

Use a single download helper in `App.vue` that calls the export API with the chosen format, reads the blob, and downloads it with the current report title.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
node --test frontend\src\researchReports.test.mjs
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/researchExport.js frontend/src/App.vue frontend/src/api.ts frontend/src/researchReports.test.mjs
git commit -m "feat: add pdf and docx export actions"
```
