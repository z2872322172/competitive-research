"""阶段 4 证据链完整溯源测试：ReportSectionEvidence 溯源字段 / 快照可用性 / 导出引用清单。"""

import io
import zipfile

import pytest

from app import models
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.services import reporting, research_service
from app.services.collection import CollectionSummary
from app.services.report_export import build_report_markdown, format_evidence_line, render_report_docx, render_report_pdf


@pytest.fixture(autouse=True)
def disable_real_search(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "")
    get_settings.cache_clear()
    init_db()
    yield
    get_settings.cache_clear()


def seed_traceable_claim(db, task, *, with_snapshot=True):
    source = models.Source(
        task_id=task.id,
        url="http://cursor.example/pricing",
        canonical_url="https://cursor.example/pricing",
        source_type="official",
        title="Cursor Pricing",
        publisher="Cursor",
        content_hash=f"{task.id}-trace-hash",
        is_primary=True,
    )
    db.add(source)
    db.flush()
    if with_snapshot:
        db.add(
            models.SourceArtifact(
                source_id=source.id,
                artifact_type="html_snapshot",
                object_key=f"snapshots/{task.id}/{source.id}.html",
                sha256=f"sha256-{source.id}",
            )
        )
        db.flush()
    evidence = models.Evidence(
        source_id=source.id,
        quote="Cursor business plan includes privacy mode.",
        locator_json=research_service.encode_json({"kind": "html", "heading": "Pricing", "char_start": 120}),
        evidence_hash=f"{source.id}-trace-evidence",
        extraction_method="trace_test",
        quality_score=0.9,
    )
    db.add(evidence)
    db.flush()
    claim = models.Claim(
        task_id=task.id,
        subject="Cursor",
        predicate="supports_feature",
        value_json=research_service.encode_json({"feature": "privacy_mode"}),
        claim_type="feature_support",
        dimension="技术能力",
        status="verified",
        confidence="high",
        confidence_score=0.9,
        evidence_coverage=1.0,
        display_text="Cursor 支持隐私模式。",
    )
    db.add(claim)
    db.flush()
    db.add(models.ClaimEvidence(claim_id=claim.id, evidence_id=evidence.id, relation="supports", weight=1.0))
    db.commit()
    return claim, evidence, source


def build_report_out(db, task, *, with_snapshot=True):
    seed_traceable_claim(db, task, with_snapshot=with_snapshot)
    summary = CollectionSummary(provider="test", searched=True, sources_created=1, evidence_created=1)
    report = reporting.create_claim_report(db, task, summary)
    return research_service.serialize_report_out(report)


def test_report_section_evidence_contains_full_traceability():
    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor pricing",
                competitors=["Cursor"],
                dimensions=["pricing"],
            ),
        )
        report_out = build_report_out(db, task)

        evidence_items = [item for section in report_out.sections for item in section.evidence]
        assert evidence_items, "报告章节应包含证据"
        item = evidence_items[0]
        assert item.source_type == "official"
        assert item.source_url == "https://cursor.example/pricing"
        assert item.reliability_score is not None
        assert item.reliability_level in {"high", "medium", "low"}
        assert item.reliability_reasons
        assert item.locator.get("heading") == "Pricing"
        assert item.snapshot_available is True
        assert item.content_hash == f"{task.id}-trace-hash"
        assert item.claim_ids
        assert item.relation == "supports"
    finally:
        db.rollback()
        db.close()


def test_report_section_evidence_marks_snapshot_unavailable_without_artifact():
    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor pricing",
                competitors=["Cursor"],
                dimensions=["pricing"],
            ),
        )
        report_out = build_report_out(db, task, with_snapshot=False)

        item = report_out.sections[0].evidence[0]
        assert item.snapshot_available is False
        assert item.content_hash is not None
    finally:
        db.rollback()
        db.close()


def test_exports_include_citation_list():
    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor pricing",
                competitors=["Cursor"],
                dimensions=["pricing"],
            ),
        )
        report_out = build_report_out(db, task)

        markdown = build_report_markdown(report_out)
        assert "### 引用来源" in markdown
        assert "https://cursor.example/pricing" in markdown
        assert "可靠性" in markdown
        assert "快照可用" in markdown

        pdf_bytes = render_report_pdf(report_out)
        assert pdf_bytes.startswith(b"%PDF") and len(pdf_bytes) > 1000

        docx_bytes = render_report_docx(report_out)
        with zipfile.ZipFile(io.BytesIO(docx_bytes)) as bundle:
            docx_text = bundle.read("word/document.xml").decode("utf-8")
        assert "Section evidence" in docx_text
        assert "https://cursor.example/pricing" in docx_text
        assert "可靠性" in docx_text
    finally:
        db.rollback()
        db.close()


def test_format_evidence_line_contains_reliability_snapshot_and_url():
    from app.schemas import ReportSectionEvidenceOut

    evidence = ReportSectionEvidenceOut(
        id=12,
        source_id=3,
        quote="q",
        source_title="Cursor Pricing",
        source_url="https://cursor.example/pricing",
        publisher="Cursor",
        source_type="official",
        quality_score=0.9,
        reliability_score=0.85,
        reliability_level="high",
        relation="supports",
        snapshot_available=True,
        claim_ids=[1, 2],
    )
    line = format_evidence_line(evidence)
    assert "12 | Cursor Pricing | 90%" in line
    assert "可靠性 85%/high" in line
    assert "supports | 2 Claims" in line
    assert "快照可用" in line
    assert "https://cursor.example/pricing" in line


def test_citation_coverage_counts_only_claims_with_evidence():
    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor pricing",
                competitors=["Cursor"],
                dimensions=["pricing"],
            ),
        )
        claim, _evidence, _source = seed_traceable_claim(db, task)

        bare_claim = models.Claim(
            task_id=task.id,
            subject="Windsurf",
            predicate="supports_feature",
            value_json="{}",
            claim_type="feature_support",
            dimension="技术能力",
            status="verified",
            confidence="high",
            confidence_score=0.8,
            evidence_coverage=0.0,
            display_text="Windsurf 支持隐私模式。",
        )
        db.add(bare_claim)
        db.commit()
        claims_with = list(db.query(models.Claim).filter_by(task_id=task.id).all())

        coverage = reporting.calculate_citation_coverage(claims_with)
        assert coverage == 0.5
    finally:
        db.rollback()
        db.close()
