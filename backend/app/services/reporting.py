import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import models


REPORT_TEMPLATE_VERSION = "stage5-review-v1"
RISKY_REPORT_CLAIM_STATUSES = {"conflict", "undisclosed", "low_confidence", "needs_evidence"}


def create_claim_report(
    db: Session,
    task: models.ResearchTask,
    summary,
    *,
    force_new_version: bool = False,
    generation_reason: str = "initial_workflow",
) -> models.Report | None:
    latest_version = db.execute(select(func.max(models.Report.version)).where(models.Report.task_id == task.id)).scalar() or 0
    if latest_version and not force_new_version:
        return None

    claims = load_report_claims(db, task.id)
    citation_coverage = calculate_citation_coverage(claims)
    input_snapshot = build_report_input_snapshot(task, claims, generation_reason)
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

    db.add_all(
        [
            models.ReportSection(
                report_id=report.id,
                section_type="executive_summary",
                title="执行摘要",
                content_markdown=render_executive_summary(task, claims),
                order_no=1,
            ),
            models.ReportSection(
                report_id=report.id,
                section_type="collection_summary",
                title="采集摘要",
                content_markdown=render_collection_summary(summary),
                order_no=2,
            ),
            models.ReportSection(
                report_id=report.id,
                section_type="key_claims",
                title="关键结论",
                content_markdown=render_key_claims(claims),
                order_no=3,
            ),
            models.ReportSection(
                report_id=report.id,
                section_type="review_risks",
                title="风险与待审阅项",
                content_markdown=render_review_risks(claims),
                order_no=4,
            ),
            models.ReportSection(
                report_id=report.id,
                section_type="citation_coverage",
                title="引用覆盖",
                content_markdown=render_citation_coverage(citation_coverage, claims),
                order_no=5,
            ),
        ]
    )
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
                {
                    "id": evidence.id,
                    "source_id": evidence.source_id,
                    "quote": evidence.quote,
                    "source_title": evidence.source.title if evidence.source else None,
                    "source_url": evidence.source.canonical_url if evidence.source else None,
                    "publisher": evidence.source.publisher if evidence.source else None,
                    "quality_score": evidence.quality_score,
                    "relation": link.relation,
                    "claim_ids": [],
                },
            )
            if claim.id not in item["claim_ids"]:
                item["claim_ids"].append(claim.id)
    return sorted(snapshots.values(), key=lambda item: (-item["quality_score"], item["id"]))


def load_report_claims(db: Session, task_id: int) -> list[models.Claim]:
    return (
        db.execute(
            select(models.Claim)
            .where(models.Claim.task_id == task_id, models.Claim.include_in_report.is_(True))
            .options(
                selectinload(models.Claim.evidence_links)
                .selectinload(models.ClaimEvidence.evidence)
                .selectinload(models.Evidence.source)
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
