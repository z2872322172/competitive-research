"""阶段 2 报告草稿实时化测试：运行草稿创建 / 阶段性发现章节 / generate_report 复用草稿逐章节覆盖 / report.section_updated 事件。"""

import pytest

from app import models
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.services import reporting, research_service
from app.services.collection import CollectionSummary


@pytest.fixture(autouse=True)
def disable_real_search(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "")
    get_settings.cache_clear()
    init_db()
    yield
    get_settings.cache_clear()


def create_demo_task_with_run(db, *, prompt="Research Cursor and Windsurf pricing"):
    task = research_service.create_task(
        db,
        research_service.ResearchTaskCreate(
            prompt=prompt,
            competitors=["Cursor", "Windsurf"],
            dimensions=["pricing"],
        ),
    )
    run = research_service.create_run(db, task.id)
    return task, run


def seed_claim_with_evidence(db, task, *, status="verified", confidence_score=0.9):
    source = models.Source(
        task_id=task.id,
        url="https://cursor.example/pricing",
        canonical_url="https://cursor.example/pricing",
        source_type="official",
        title="Cursor Pricing",
        publisher="Cursor",
        content_hash=f"{task.id}-draft-source",
        is_primary=True,
    )
    db.add(source)
    db.flush()
    evidence = models.Evidence(
        source_id=source.id,
        quote="Cursor business plan includes privacy mode and admin controls.",
        locator_json=research_service.encode_json({"kind": "html", "heading": "Pricing"}),
        evidence_hash=f"{source.id}-draft-evidence",
        extraction_method="draft_test",
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
        status=status,
        confidence="high" if confidence_score >= 0.75 else "low",
        confidence_score=confidence_score,
        evidence_coverage=1.0,
        display_text="Cursor 在企业隐私控制上能力成熟。",
    )
    db.add(claim)
    db.flush()
    db.add(models.ClaimEvidence(claim_id=claim.id, evidence_id=evidence.id, relation="supports", weight=1.0))
    db.commit()
    return claim


def section_types(db, report_id):
    return {
        section.section_type
        for section in db.query(models.ReportSection).filter_by(report_id=report_id).all()
    }


def test_ensure_run_draft_report_creates_v1_with_research_plan_section_and_event():
    db = SessionLocal()
    try:
        task, run = create_demo_task_with_run(db)

        report = reporting.ensure_run_draft_report(db, task, run_id=run.id)

        assert report is not None
        assert report.version == 1
        assert report.status == "draft"
        assert report.generated_at is None
        assert section_types(db, report.id) == {"research_plan"}
        research_plan = db.query(models.ReportSection).filter_by(report_id=report.id, section_type="research_plan").one()
        assert "研究问题：" in research_plan.content_markdown
        assert "Cursor" in research_plan.content_markdown

        events = (
            db.query(models.ResearchEvent)
            .filter_by(run_id=run.id, type="report.section_updated")
            .all()
        )
        assert len(events) == 1
        payload = research_service.decode_json(events[0].payload_json)
        assert payload["section_type"] == "research_plan"
        assert payload["version"] == 1

        # 幂等：重复调用不新建报告
        assert reporting.ensure_run_draft_report(db, task, run_id=run.id).id == report.id
        assert db.query(models.Report).filter_by(task_id=task.id).count() == 1
    finally:
        db.rollback()
        db.close()


def test_update_interim_findings_section_upserts_into_run_draft():
    db = SessionLocal()
    try:
        task, run = create_demo_task_with_run(db)
        reporting.ensure_run_draft_report(db, task, run_id=run.id)
        seed_claim_with_evidence(db, task)

        reporting.update_interim_findings_section(db, task, run_id=run.id)

        report = reporting.latest_task_report(db, task.id)
        assert "interim_findings" in section_types(db, report.id)
        interim = db.query(models.ReportSection).filter_by(report_id=report.id, section_type="interim_findings").one()
        assert "1 条候选结论" in interim.content_markdown
        assert "Cursor 在企业隐私控制上能力成熟。" in interim.content_markdown

        events = (
            db.query(models.ResearchEvent)
            .filter_by(run_id=run.id, type="report.section_updated")
            .all()
        )
        assert {research_service.decode_json(e.payload_json)["section_type"] for e in events} == {
            "research_plan",
            "interim_findings",
        }
    finally:
        db.rollback()
        db.close()


def test_create_claim_report_reuses_unfinalized_draft_and_writes_sections_incrementally():
    db = SessionLocal()
    try:
        task, run = create_demo_task_with_run(db)
        reporting.ensure_run_draft_report(db, task, run_id=run.id)
        reporting.update_interim_findings_section(db, task, run_id=run.id)
        seed_claim_with_evidence(db, task)
        summary = CollectionSummary(provider="test", searched=True, sources_created=1, evidence_created=1)

        report = reporting.create_claim_report(db, task, summary, run_id=run.id)

        # 复用同一个 v1 草稿，不新建版本
        assert report.version == 1
        assert db.query(models.Report).filter_by(task_id=task.id).count() == 1
        assert report.generated_at is not None

        final_types = {
            "research_plan",
            "executive_summary",
            "collection_summary",
            "key_claims",
            "review_risks",
            "citation_coverage",
        }
        assert section_types(db, report.id) == final_types
        # 阶段性发现章节在最终覆盖后被移除
        assert "interim_findings" not in section_types(db, report.id)

        section_events = [
            research_service.decode_json(e.payload_json)["section_type"]
            for e in db.query(models.ResearchEvent)
            .filter_by(run_id=run.id, type="report.section_updated")
            .order_by(models.ResearchEvent.sequence_no)
            .all()
        ]
        assert section_events == [
            "research_plan",
            "interim_findings",
            "executive_summary",
            "collection_summary",
            "key_claims",
            "review_risks",
            "citation_coverage",
        ]
    finally:
        db.rollback()
        db.close()


def test_create_claim_report_returns_none_for_finalized_report_without_force():
    db = SessionLocal()
    try:
        task, run = create_demo_task_with_run(db)
        reporting.ensure_run_draft_report(db, task, run_id=run.id)
        seed_claim_with_evidence(db, task)
        summary = CollectionSummary(provider="test", searched=True, sources_created=1, evidence_created=1)

        first = reporting.create_claim_report(db, task, summary, run_id=run.id)
        assert first is not None
        # 已 finalize 的报告：非强制调用保持幂等
        assert reporting.create_claim_report(db, task, summary) is None
        assert db.query(models.Report).filter_by(task_id=task.id).count() == 1

        # 强制重生成创建 v2
        second = reporting.create_claim_report(db, task, summary, force_new_version=True, generation_reason="after_review")
        assert second.version == 2
        assert db.query(models.Report).filter_by(task_id=task.id).count() == 2
    finally:
        db.rollback()
        db.close()


def test_update_interim_findings_skips_finalized_report():
    db = SessionLocal()
    try:
        task, run = create_demo_task_with_run(db)
        reporting.ensure_run_draft_report(db, task, run_id=run.id)
        seed_claim_with_evidence(db, task)
        summary = CollectionSummary(provider="test", searched=True, sources_created=1, evidence_created=1)
        report = reporting.create_claim_report(db, task, summary, run_id=run.id)

        reporting.update_interim_findings_section(db, task, run_id=run.id)

        assert "interim_findings" not in section_types(db, report.id)
    finally:
        db.rollback()
        db.close()


def test_workflow_generates_incremental_report_sections_e2e():
    from app.workflows.research_graph import run_research_workflow

    db = SessionLocal()
    try:
        task, run = create_demo_task_with_run(db)

        run_research_workflow(db, run.id)

        reports = db.query(models.Report).filter_by(task_id=task.id).all()
        assert len(reports) == 1
        report = reports[0]
        assert report.version == 1

        # demo 路径：研究计划章节 + demo 章节共存于同一份 v1 草稿
        types = section_types(db, report.id)
        assert "research_plan" in types
        assert "executive_summary" in types

        section_events = [
            research_service.decode_json(e.payload_json)["section_type"]
            for e in db.query(models.ResearchEvent)
            .filter_by(run_id=run.id, type="report.section_updated")
            .order_by(models.ResearchEvent.sequence_no)
            .all()
        ]
        assert section_events[0] == "research_plan"
        assert len(section_events) >= 3
    finally:
        db.rollback()
        db.close()
