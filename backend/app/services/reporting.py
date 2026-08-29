import json

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.services.source_quality import score_source_reliability

REPORT_TEMPLATE_VERSION = "stage5-review-v1"
RISKY_REPORT_CLAIM_STATUSES = {"conflict", "undisclosed", "low_confidence", "needs_evidence"}

RESEARCH_PLAN_SECTION_TYPE = "research_plan"
INTERIM_FINDINGS_SECTION_TYPE = "interim_findings"
RESEARCH_PLAN_ORDER_NO = 0
INTERIM_FINDINGS_ORDER_NO = 6


def latest_task_report(db: Session, task_id: int) -> models.Report | None:
    return (
        db.execute(
            select(models.Report)
            .where(models.Report.task_id == task_id)
            .order_by(models.Report.version.desc(), models.Report.id.desc())
        )
        .scalars()
        .first()
    )


def is_unfinalized_run_draft(db: Session, report: models.Report) -> bool:
    """判断报告是否为工作流运行中的草稿（尚未被 generate_report 填充最终章节）。"""
    if report is None or report.status != "draft":
        return False
    return (
        db.query(models.ReportSection.id)
        .filter_by(report_id=report.id, section_type="executive_summary")
        .first()
        is None
    )


def append_report_section_event(
    db: Session,
    *,
    run_id: int | None,
    report: models.Report,
    section_type: str,
    title: str,
    stage: str = "generate_report",
) -> None:
    if run_id is None:
        return
    # 延迟导入避免与 research_service 的循环依赖
    from app.services.research_service import append_event

    append_event(
        db,
        run_id=run_id,
        event_type="report.section_updated",
        stage=stage,
        message=f"报告草稿已更新章节「{title}」。",
        payload={
            "report_id": report.id,
            "version": report.version,
            "section_type": section_type,
            "title": title,
            "order_no": RESEARCH_PLAN_ORDER_NO if section_type == RESEARCH_PLAN_SECTION_TYPE else INTERIM_FINDINGS_ORDER_NO if section_type == INTERIM_FINDINGS_SECTION_TYPE else FINAL_SECTION_ORDER.get(section_type),
        },
    )


def upsert_report_section(
    db: Session,
    report: models.Report,
    *,
    section_type: str,
    title: str,
    content_markdown: str,
    order_no: int,
) -> models.ReportSection:
    section = db.query(models.ReportSection).filter_by(report_id=report.id, section_type=section_type).first()
    if section is None:
        section = models.ReportSection(report_id=report.id, section_type=section_type, order_no=order_no)
        db.add(section)
    section.title = title
    section.content_markdown = content_markdown
    section.order_no = order_no
    db.flush()
    return section


def render_research_plan(task: models.ResearchTask, scope: dict) -> str:
    lines = [f"研究问题：{task.prompt}"]
    competitors = [str(item) for item in scope.get("competitors") or [] if str(item).strip()]
    dimensions = [str(item) for item in scope.get("dimensions") or [] if str(item).strip()]
    source_preferences = [str(item) for item in scope.get("source_preferences") or [] if str(item).strip()]
    if competitors:
        lines.append(f"研究对象：{'、'.join(competitors)}")
    if dimensions:
        lines.append(f"分析维度：{'、'.join(dimensions)}")
    if source_preferences:
        lines.append(f"来源策略：{'、'.join(source_preferences)}")
    lines.append("")
    lines.append("本报告将随研究推进逐步生成：来源采集与证据抽取完成后更新阶段性发现，全部结论验证完成后生成本报告。")
    return "\n".join(lines)


def render_interim_findings(claims: list[models.Claim]) -> str:
    if not claims:
        return "- 证据与结论抽取进行中，阶段性发现将在 Claim 验证完成后更新。"
    high_confidence = sum(1 for claim in claims if claim.confidence == "high")
    risky = sum(1 for claim in claims if claim.status in RISKY_REPORT_CLAIM_STATUSES)
    lines = [
        f"当前已形成 {len(claims)} 条候选结论（高置信度 {high_confidence} 条，需关注 {risky} 条）。",
        "",
        "以下为阶段性发现：",
    ]
    lines.extend(f"- {claim.display_text}" for claim in claims)
    return "\n".join(lines)


def ensure_run_draft_report(
    db: Session,
    task: models.ResearchTask,
    *,
    run_id: int | None = None,
    stage: str = "initialize_run",
) -> models.Report | None:
    """工作流启动时确保存在运行草稿报告（v1），含研究计划章节；已存在报告则直接返回。"""
    existing = latest_task_report(db, task.id)
    if existing is not None:
        return existing
    try:
        scope = json.loads(task.scope_json or "{}")
    except json.JSONDecodeError:
        scope = {}
    report = models.Report(
        task_id=task.id,
        version=1,
        status="draft",
        citation_coverage=0.0,
        input_snapshot_json=task.scope_json or "{}",
        generated_at=None,
    )
    db.add(report)
    db.flush()
    upsert_report_section(
        db,
        report,
        section_type=RESEARCH_PLAN_SECTION_TYPE,
        title="研究计划",
        content_markdown=render_research_plan(task, scope),
        order_no=RESEARCH_PLAN_ORDER_NO,
    )
    append_report_section_event(
        db,
        run_id=run_id,
        report=report,
        section_type=RESEARCH_PLAN_SECTION_TYPE,
        title="研究计划",
        stage=stage,
    )
    db.commit()
    return report


def update_interim_findings_section(
    db: Session,
    task: models.ResearchTask,
    *,
    run_id: int | None = None,
    stage: str = "verify_claims",
) -> models.Report | None:
    """Claim 验证完成后更新草稿报告的阶段性发现章节（仅对未 finalize 的运行草稿生效）。"""
    report = ensure_run_draft_report(db, task, run_id=run_id, stage=stage)
    if report is None or not is_unfinalized_run_draft(db, report):
        return report
    claims = load_report_claims(db, task.id)
    upsert_report_section(
        db,
        report,
        section_type=INTERIM_FINDINGS_SECTION_TYPE,
        title="阶段性发现",
        content_markdown=render_interim_findings(claims),
        order_no=INTERIM_FINDINGS_ORDER_NO,
    )
    append_report_section_event(
        db,
        run_id=run_id,
        report=report,
        section_type=INTERIM_FINDINGS_SECTION_TYPE,
        title="阶段性发现",
        stage=stage,
    )
    db.commit()
    return report


FINAL_SECTION_ORDER = {
    "executive_summary": 1,
    "collection_summary": 2,
    "key_claims": 3,
    "review_risks": 4,
    "citation_coverage": 5,
}


def create_claim_report(
    db: Session,
    task: models.ResearchTask,
    summary,
    *,
    force_new_version: bool = False,
    generation_reason: str = "initial_workflow",
    run_id: int | None = None,
) -> models.Report | None:
    existing = latest_task_report(db, task.id)
    reuse_draft = (
        existing is not None
        and not force_new_version
        and generation_reason == "initial_workflow"
        and is_unfinalized_run_draft(db, existing)
    )
    if existing is not None and not reuse_draft and not force_new_version:
        return None

    claims = load_report_claims(db, task.id)
    citation_coverage = calculate_citation_coverage(claims)
    input_snapshot = build_report_input_snapshot(task, claims, generation_reason)

    if reuse_draft:
        report = existing
        report.citation_coverage = citation_coverage
        report.input_snapshot_json = json.dumps(input_snapshot, ensure_ascii=False)
        report.generated_at = models.utc_now()
        db.flush()
    else:
        latest_version = existing.version if existing is not None else 0
        report = models.Report(
            task_id=task.id,
            version=latest_version + 1,
            status="draft",
            citation_coverage=citation_coverage,
            input_snapshot_json=json.dumps(input_snapshot, ensure_ascii=False),
            generated_at=models.utc_now(),
        )
        db.add(report)
        db.flush()

    section_specs = [
        ("executive_summary", "执行摘要", render_executive_summary(task, claims)),
        ("collection_summary", "采集摘要", render_collection_summary(summary)),
        ("key_claims", "关键结论", render_key_claims(claims)),
        ("review_risks", "风险与待审阅项", render_review_risks(claims)),
        ("citation_coverage", "引用覆盖", render_citation_coverage(citation_coverage, claims)),
    ]
    for section_type, title, content_markdown in section_specs:
        upsert_report_section(
            db,
            report,
            section_type=section_type,
            title=title,
            content_markdown=content_markdown,
            order_no=FINAL_SECTION_ORDER[section_type],
        )
        append_report_section_event(
            db,
            run_id=run_id,
            report=report,
            section_type=section_type,
            title=title,
        )

    # 最终章节就位后移除阶段性发现章节，避免与关键结论重复
    interim_section = (
        db.query(models.ReportSection)
        .filter_by(report_id=report.id, section_type=INTERIM_FINDINGS_SECTION_TYPE)
        .first()
    )
    if interim_section is not None:
        db.delete(interim_section)

    db.commit()
    db.refresh(report)
    return report


def build_report_input_snapshot(task: models.ResearchTask, claims: list[models.Claim], generation_reason: str) -> dict:
    try:
        scope = json.loads(task.scope_json or "{}")
    except json.JSONDecodeError:
        scope = {}
    return {
        **scope,
        "report_generation": {
            "reason": generation_reason,
            "template_version": REPORT_TEMPLATE_VERSION,
            "included_claim_ids": [claim.id for claim in claims],
            "included_claim_count": len(claims),
            "risk_claim_count": sum(1 for claim in claims if claim.status in RISKY_REPORT_CLAIM_STATUSES),
            "section_evidence": build_section_evidence_snapshots(claims),
        },
    }


def build_section_evidence_snapshots(claims: list[models.Claim]) -> dict[str, list[dict]]:
    all_evidence = build_evidence_snapshots(claims)
    risky_evidence = build_evidence_snapshots([claim for claim in claims if claim.status in RISKY_REPORT_CLAIM_STATUSES])
    return {
        "executive_summary": all_evidence,
        "collection_summary": [],
        "key_claims": all_evidence,
        "review_risks": risky_evidence,
        "citation_coverage": all_evidence,
        "comparison": all_evidence,
    }


def build_evidence_snapshots(claims: list[models.Claim]) -> list[dict]:
    snapshots: dict[str, dict] = {}
    for claim in claims:
        for link in claim.evidence_links:
            evidence = link.evidence
            if evidence is None:
                continue
            item = snapshots.setdefault(
                evidence.id,
                build_single_evidence_snapshot(evidence, relation=link.relation),
            )
            if claim.id not in item["claim_ids"]:
                item["claim_ids"].append(claim.id)
    return sorted(snapshots.values(), key=lambda item: (-item["quality_score"], item["id"]))


def build_single_evidence_snapshot(evidence: models.Evidence, *, relation: str | None) -> dict:
    source = evidence.source
    reliability = score_source_reliability(source) if source is not None else None
    try:
        locator = json.loads(evidence.locator_json or "{}")
    except json.JSONDecodeError:
        locator = {}
    if not isinstance(locator, dict):
        locator = {}
    return {
        "id": evidence.id,
        "source_id": evidence.source_id,
        "quote": evidence.quote,
        "source_title": source.title if source else None,
        "source_url": source.canonical_url if source else None,
        "publisher": source.publisher if source else None,
        "source_type": source.source_type if source else None,
        "quality_score": evidence.quality_score,
        "reliability_score": reliability["score"] if reliability else None,
        "reliability_level": reliability["label"] if reliability else None,
        "reliability_reasons": reliability["reasons"] if reliability else [],
        "relation": relation,
        "locator": locator,
        "snapshot_available": has_source_snapshot(source),
        "content_hash": source.content_hash if source else None,
        "claim_ids": [],
    }


def has_source_snapshot(source: models.Source | None) -> bool:
    if source is None:
        return False
    artifacts = getattr(source, "artifacts", None) or []
    return any(artifact.artifact_type == "html_snapshot" for artifact in artifacts)


def load_report_claims(db: Session, task_id: int) -> list[models.Claim]:
    return (
        db.execute(
            select(models.Claim)
            .where(models.Claim.task_id == task_id, models.Claim.include_in_report.is_(True))
            .options(
                selectinload(models.Claim.evidence_links)
                .selectinload(models.ClaimEvidence.evidence)
                .selectinload(models.Evidence.source)
                .selectinload(models.Source.artifacts)
            )
            .order_by(models.Claim.confidence_score.desc(), models.Claim.created_at.asc())
            .limit(12)
        )
        .scalars()
        .all()
    )


def calculate_citation_coverage(claims: list[models.Claim]) -> float:
    if not claims:
        return 0.0
    cited = sum(1 for claim in claims if claim.evidence_links)
    return round(cited / len(claims), 4)


def render_executive_summary(task: models.ResearchTask, claims: list[models.Claim]) -> str:
    if not claims:
        return f"本报告基于任务“{task.title}”生成，当前尚未形成可入报的结构化 Claim。"
    high_confidence = sum(1 for claim in claims if claim.confidence == "high")
    risky = sum(1 for claim in claims if claim.status in {"conflict", "undisclosed", "low_confidence", "needs_evidence"})
    return (
        f"本报告基于任务“{task.title}”生成，共纳入 {len(claims)} 条结构化 Claim，"
        f"其中高置信度结论 {high_confidence} 条，需关注或审阅的结论 {risky} 条。"
        f"\n\n模板版本：`{REPORT_TEMPLATE_VERSION}`。"
    )


def render_collection_summary(summary) -> str:
    return (
        f"本轮通过 {summary.provider} 发现 {summary.source_candidates} 个候选来源，"
        f"成功入库 {summary.sources_created} 个 Source，抽取 {summary.evidence_created} 条 Evidence。"
        f"跳过低质量来源 {summary.low_quality_sources} 个，robots 阻止 {summary.robots_blocked} 个。"
    )


def render_key_claims(claims: list[models.Claim]) -> str:
    if not claims:
        return "- 本轮尚未生成可入报的结构化 Claim。"
    lines = []
    for claim in claims:
        evidence_refs = ", ".join(str(link.evidence_id) for link in claim.evidence_links) or "暂无绑定 Evidence"
        lines.append(f"- {claim.display_text} Evidence: {evidence_refs}")
    return "\n".join(lines)


def render_review_risks(claims: list[models.Claim]) -> str:
    risky = [claim for claim in claims if claim.status in {"conflict", "undisclosed", "low_confidence", "needs_evidence"}]
    if not risky:
        return "- 暂无必须人工处理的风险结论。"
    return "\n".join(f"- [{claim.status}] {claim.display_text}" for claim in risky)


def render_citation_coverage(citation_coverage: float, claims: list[models.Claim]) -> str:
    cited = sum(1 for claim in claims if claim.evidence_links)
    return f"引用覆盖率：{citation_coverage:.0%}（{cited}/{len(claims)} 条 Claim 已绑定 Evidence）。"
