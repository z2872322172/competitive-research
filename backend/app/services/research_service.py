import hashlib
import json
from datetime import datetime
from html import escape as escape_html
from time import sleep
from typing import Any

import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.config import get_settings
from app.schemas import (
    ClaimOut,
    CompetitorProfileCreate,
    CompetitorProfileOut,
    CompetitorSourceUrl,
    EvidenceOut,
    ResearchEventOut,
    ResearchTaskCreate,
    ResearchTaskOut,
    ReportOut,
    ReportSectionEvidenceOut,
    ReportSectionOut,
    SourceOut,
    SourceSnapshotOut,
    TaskDetailOut,
    TaskRunOut,
)
from app.services.analysis.claim_extractor import extract_and_store_claims
from app.services.collection import (
    CollectionSummary,
    collect_research_evidence,
    create_claim_report,
    discover_research_sources,
    extract_research_evidence,
    fetch_research_sources,
    parse_research_sources,
)
from app.services.parsing.html_parser import parse_html
from app.services.storage.artifacts import build_artifact_storage
from app.services.reporting import build_section_evidence_snapshots


STAGES = [
    ("planning.started", "plan_research", "已解析研究目标，生成竞品、维度和来源策略。"),
    ("search.started", "discover_sources", "已派发官方网页、文档和新闻来源检索。"),
    ("source.found", "fetch_source", "发现并保存核心来源快照。"),
    ("evidence.created", "extract_evidence", "已抽取可引用 Evidence，并记录原文定位。"),
    ("claim.created", "verify_claims", "已生成结构化 Claim，并完成基础置信度评分。"),
    ("review.required", "review_gate", "发现冲突和未披露项，等待人工审阅。"),
    ("report.created", "generate_report", "已生成带引用的 Markdown 报告草稿。"),
]

TASK_TRANSITIONS: dict[str, set[str]] = {
    models.TaskStatus.draft.value: {models.TaskStatus.confirmed.value, models.TaskStatus.canceled.value},
    models.TaskStatus.confirmed.value: {models.TaskStatus.queued.value, models.TaskStatus.canceled.value},
    models.TaskStatus.queued.value: {models.TaskStatus.running.value, models.TaskStatus.failed.value, models.TaskStatus.canceled.value},
    models.TaskStatus.running.value: {
        models.TaskStatus.waiting_review.value,
        models.TaskStatus.completed.value,
        models.TaskStatus.failed.value,
        models.TaskStatus.canceled.value,
    },
    models.TaskStatus.waiting_review.value: {
        models.TaskStatus.queued.value,
        models.TaskStatus.completed.value,
        models.TaskStatus.running.value,
        models.TaskStatus.failed.value,
        models.TaskStatus.canceled.value,
    },
    models.TaskStatus.failed.value: {models.TaskStatus.queued.value},
    models.TaskStatus.completed.value: {models.TaskStatus.queued.value},
    models.TaskStatus.canceled.value: {models.TaskStatus.queued.value},
}

ACTIVE_RUN_STATUSES = {models.RunStatus.queued.value, models.RunStatus.running.value}
REPORT_MAX_ATTEMPTS = 3
RISKY_CLAIM_STATUSES = {
    models.ClaimStatus.conflict.value,
    models.ClaimStatus.low_confidence.value,
    models.ClaimStatus.undisclosed.value,
    models.ClaimStatus.needs_evidence.value,
}
DEFAULT_WORKSPACE_ID = "default"
COMPETITIVE_RESEARCH_TYPE = "competitive_research"
DEEP_RESEARCH_TYPE = "deep_research"
DEFAULT_COMPETITIVE_TEMPLATE = "competitive_research"
DEFAULT_DEEP_RESEARCH_TEMPLATE = "generic_deep_research"


def encode_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def decode_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    return json.loads(value)


def infer_title(payload: ResearchTaskCreate) -> str:
    if payload.title:
        return payload.title
    first_line = payload.prompt.strip().splitlines()[0]
    return first_line[:60]


def clean_text_list(values: list[str]) -> list[str]:
    return [item.strip() for item in values if item.strip()]


def infer_research_type(payload: ResearchTaskCreate, competitors: list[str]) -> str:
    if payload.research_type:
        return payload.research_type
    return COMPETITIVE_RESEARCH_TYPE if competitors else DEEP_RESEARCH_TYPE


def infer_template(payload: ResearchTaskCreate, research_type: str) -> str:
    if payload.template and payload.template.strip():
        return payload.template.strip()
    if research_type == COMPETITIVE_RESEARCH_TYPE:
        return DEFAULT_COMPETITIVE_TEMPLATE
    return DEFAULT_DEEP_RESEARCH_TEMPLATE


def create_task(db: Session, payload: ResearchTaskCreate) -> models.ResearchTask:
    competitors = clean_text_list(payload.competitors)
    dimensions = clean_text_list(payload.dimensions)
    research_aspects = clean_text_list(payload.research_aspects) or dimensions
    if not dimensions:
        dimensions = research_aspects
    research_type = infer_research_type(payload, competitors)
    template = infer_template(payload, research_type)
    research_question = (payload.research_question or payload.prompt).strip()
    source_preferences, competitor_profile_reuse = reuse_competitor_profile_sources(
        db,
        competitors=competitors,
        source_preferences=clean_text_list(payload.source_preferences),
    )
    scope = {
        "research_type": research_type,
        "template": template,
        "research_question": research_question,
        "research_aspects": research_aspects,
        "competitors": competitors,
        "dimensions": dimensions,
        "source_preferences": source_preferences,
        "competitor_profile_reuse": competitor_profile_reuse,
        "report_depth": payload.report_depth,
        "time_range": payload.time_range,
        "output_format": payload.output_format,
        "budget": {
            "max_search_rounds": 3,
            "max_candidate_sources": 60,
            "max_valid_sources": 30,
            "max_runtime_minutes": 20,
        },
    }
    task = models.ResearchTask(
        title=infer_title(payload),
        prompt=payload.prompt,
        scope_json=encode_json(scope),
        status=models.TaskStatus.draft.value,
        workspace_id=payload.workspace_id.strip() or DEFAULT_WORKSPACE_ID,
        created_by=payload.created_by.strip() or "local-user",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def reuse_competitor_profile_sources(
    db: Session,
    *,
    competitors: list[str],
    source_preferences: list[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    normalized_competitors = [item.strip() for item in competitors if item.strip()]
    if not normalized_competitors:
        return source_preferences, []

    profiles = (
        db.execute(
            select(models.CompetitorProfile).where(
                models.CompetitorProfile.workspace_id == DEFAULT_WORKSPACE_ID,
            )
        )
        .scalars()
        .all()
    )
    profiles_by_name = {profile.name.strip().lower(): profile for profile in profiles}
    merged_preferences: list[str] = []
    seen_urls: set[str] = set()
    for url in source_preferences:
        normalized_url = url.strip()
        if normalized_url and normalized_url not in seen_urls:
            merged_preferences.append(normalized_url)
            seen_urls.add(normalized_url)

    reused_profiles: list[dict[str, Any]] = []
    for competitor in normalized_competitors:
        profile = profiles_by_name.get(competitor.lower())
        if profile is None:
            continue
        source_urls = decode_source_urls(profile.source_urls_json)
        normalized_sources: list[dict[str, str]] = []
        for item in source_urls:
            label = str(item.get("label", "")).strip() or "Source"
            url = str(item.get("url", "")).strip()
            source_type = str(item.get("source_type", "official")).strip() or "official"
            if not url:
                continue
            normalized_sources.append({"label": label, "url": url, "source_type": source_type})
            if url not in seen_urls:
                merged_preferences.append(url)
                seen_urls.add(url)
        if normalized_sources:
            reused_profiles.append(
                {
                    "profile_id": profile.id,
                    "name": profile.name,
                    "source_count": len(normalized_sources),
                    "source_urls": normalized_sources,
                }
            )
    return merged_preferences, reused_profiles


def transition_task(task: models.ResearchTask, target_status: models.TaskStatus, *, reason: str | None = None) -> None:
    current_status = task.status
    next_status = target_status.value
    if current_status == next_status:
        return
    if next_status not in TASK_TRANSITIONS.get(current_status, set()):
        raise ValueError(f"invalid_task_transition:{current_status}:{next_status}")

    now = models.utc_now()
    task.status = next_status
    if target_status == models.TaskStatus.confirmed:
        task.confirmed_at = now
    if target_status == models.TaskStatus.queued:
        task.queued_at = now
        task.completed_at = None
        task.failure_reason = None
    if target_status == models.TaskStatus.completed:
        task.completed_at = now
    if target_status == models.TaskStatus.failed:
        task.failure_reason = reason


def get_latest_run(db: Session, task_id: str) -> models.TaskRun | None:
    return (
        db.execute(
            select(models.TaskRun)
            .where(models.TaskRun.task_id == task_id)
            .order_by(models.TaskRun.queued_at.desc().nullslast(), models.TaskRun.started_at.desc().nullslast(), models.TaskRun.id.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def create_run(db: Session, task_id: str, *, allow_rerun: bool = False, priority: int = 5) -> models.TaskRun:
    task = db.get(models.ResearchTask, task_id)
    if task is None:
        raise ValueError("task_not_found")

    latest_run = get_latest_run(db, task_id)
    if latest_run and latest_run.status in ACTIVE_RUN_STATUSES:
        raise ValueError("task_already_running")
    if not allow_rerun and task.status != models.TaskStatus.draft.value:
        raise ValueError("task_not_confirmable")
    if allow_rerun and task.status == models.TaskStatus.running.value:
        raise ValueError("task_already_running")

    if not allow_rerun:
        transition_task(task, models.TaskStatus.confirmed)
    transition_task(task, models.TaskStatus.queued)

    run = models.TaskRun(
        task_id=task_id,
        status=models.RunStatus.queued.value,
        current_stage="queued",
        priority=priority,
        input_snapshot_json=task.scope_json,
        queued_at=task.queued_at or models.utc_now(),
    )
    db.add(run)
    db.flush()
    task.current_run_id = run.id
    db.commit()
    db.refresh(run)
    return run


def prepare_failed_run_resume(db: Session, task_id: str) -> models.TaskRun:
    task = db.get(models.ResearchTask, task_id)
    if task is None:
        raise ValueError("task_not_found")

    latest_run = get_latest_run(db, task_id)
    if latest_run is None:
        raise ValueError("task_run_not_found")
    if latest_run.status != models.RunStatus.failed.value or task.status != models.TaskStatus.failed.value:
        raise ValueError("task_not_resumable")

    from app.workflows.research_graph import latest_success_checkpoint

    checkpoint = latest_success_checkpoint(db, latest_run.id)
    if checkpoint is None:
        raise ValueError("resume_checkpoint_not_found")

    transition_task(task, models.TaskStatus.queued)
    latest_run.status = models.RunStatus.queued.value
    latest_run.current_stage = checkpoint.resume_node
    latest_run.error_message = None
    latest_run.finished_at = None
    task.current_run_id = latest_run.id
    append_event(
        db,
        run_id=latest_run.id,
        event_type="run.resume_requested",
        stage=checkpoint.resume_node,
        message=f"已从最近成功 checkpoint 准备继续执行：{checkpoint.resume_node}",
        payload={
            "checkpoint_id": checkpoint.id,
            "checkpoint_node": checkpoint.node_name,
            "resume_node": checkpoint.resume_node,
        },
    )
    db.commit()
    db.refresh(latest_run)
    return latest_run


def append_event(
    db: Session,
    *,
    run_id: str,
    event_type: str,
    stage: str,
    message: str,
    payload: dict[str, Any] | None = None,
    severity: str = "info",
) -> models.ResearchEvent:
    last_sequence = (
        db.execute(
            select(models.ResearchEvent.sequence_no)
            .where(models.ResearchEvent.run_id == run_id)
            .order_by(models.ResearchEvent.sequence_no.desc())
            .limit(1)
        )
        .scalar_one_or_none()
        or 0
    )
    event = models.ResearchEvent(
        run_id=run_id,
        sequence_no=last_sequence + 1,
        type=event_type,
        stage=stage,
        message=message,
        payload_json=encode_json(payload or {}),
        severity=severity,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def simulate_research_run(db: Session, run_id: str, delay_seconds: float = 0.0) -> models.TaskRun:
    from app.workflows.research_graph import run_research_workflow

    return run_research_workflow(db, run_id, delay_seconds=delay_seconds)


def run_linear_research_flow(db: Session, run_id: str, delay_seconds: float = 0.0) -> models.TaskRun:
    run = db.get(models.TaskRun, run_id)
    if run is None:
        raise ValueError("run_not_found")
    task = db.get(models.ResearchTask, run.task_id)
    if task is None:
        raise ValueError("task_not_found")

    run.status = models.RunStatus.running.value
    run.current_stage = "plan_research"
    run.started_at = models.utc_now()
    transition_task(task, models.TaskStatus.running)
    db.commit()

    event_type, stage, message = STAGES[0]
    run.current_stage = stage
    append_event(db, run_id=run.id, event_type=event_type, stage=stage, message=message)
    if delay_seconds:
        sleep(delay_seconds)

    def write_event(event_type: str, stage: str, message: str, payload: dict[str, Any] | None = None) -> None:
        run.current_stage = stage
        append_event(db, run_id=run.id, event_type=event_type, stage=stage, message=message, payload=payload)

    summary = collect_research_evidence(db, task=task, run=run, settings=get_settings(), write_event=write_event)

    if summary.evidence_created:
        claim_result = extract_and_store_claims(db, task=task, settings=get_settings())
        run.current_stage = "verify_claims"
        append_event(
            db,
            run_id=run.id,
            event_type="claim.created",
            stage="verify_claims",
            message=f"已从 Evidence 生成 {len(claim_result.claims)} 条结构化 Claim。",
            payload={"claims_created": len(claim_result.claims), "extractor": "llm_or_rule_based"},
        )
        generate_report_with_retry(db, task=task, run=run, summary=summary)
        run.current_stage = "generate_report"
        append_event(
            db,
            run_id=run.id,
            event_type="report.created",
            stage="generate_report",
            message="已生成基于 Evidence 和 Claim 的结构化报告草稿。",
            payload={"sources_created": summary.sources_created, "evidence_created": summary.evidence_created, "claims_created": len(claim_result.claims)},
        )
    else:
        for event_type, stage, message in STAGES[1:3]:
            run.current_stage = stage
            append_event(db, run_id=run.id, event_type=event_type, stage=stage, message=message)
            if delay_seconds:
                sleep(delay_seconds)

        seed_demo_research_objects(db, task.id)

        for event_type, stage, message in STAGES[3:]:
            run.current_stage = stage
            append_event(db, run_id=run.id, event_type=event_type, stage=stage, message=message)
            if delay_seconds:
                sleep(delay_seconds)

    run.status = models.RunStatus.waiting_review.value
    run.current_stage = "review_gate"
    transition_task(task, models.TaskStatus.waiting_review)
    run.finished_at = models.utc_now()
    db.commit()
    db.refresh(run)
    return run


def generate_report_with_retry(
    db: Session,
    *,
    task: models.ResearchTask,
    run: models.TaskRun,
    summary,
    force_new_version: bool = False,
    generation_reason: str = "initial_workflow",
) -> models.Report | None:
    last_error: Exception | None = None
    for attempt in range(1, REPORT_MAX_ATTEMPTS + 1):
        try:
            if not force_new_version and generation_reason == "initial_workflow":
                return create_claim_report(db, task, summary)
            return create_claim_report(
                db,
                task,
                summary,
                force_new_version=force_new_version,
                generation_reason=generation_reason,
            )
        except Exception as exc:
            db.rollback()
            last_error = exc
            append_event(
                db,
                run_id=run.id,
                event_type="report.generate_failed",
                stage="generate_report",
                message=f"报告生成第 {attempt} 次失败：{exc}",
                payload={"attempt": attempt, "max_attempts": REPORT_MAX_ATTEMPTS, "error": str(exc)},
                severity="warning" if attempt < REPORT_MAX_ATTEMPTS else "error",
            )
    raise RuntimeError(f"report_generation_failed:{last_error}")


def build_review_report_summary(db: Session, task_id: str) -> CollectionSummary:
    source_count = db.execute(select(models.Source.id).where(models.Source.task_id == task_id)).all()
    evidence_count = (
        db.execute(
            select(models.Evidence.id)
            .join(models.Source, models.Evidence.source_id == models.Source.id)
            .where(models.Source.task_id == task_id)
        )
        .all()
    )
    return CollectionSummary(
        provider="reviewed_claims",
        searched=False,
        source_candidates=len(source_count),
        sources_created=len(source_count),
        evidence_created=len(evidence_count),
    )


def regenerate_report_after_review(db: Session, *, task: models.ResearchTask, run: models.TaskRun) -> models.Report | None:
    run.status = models.RunStatus.running.value
    run.current_stage = "generate_report"
    run.finished_at = None
    transition_task(task, models.TaskStatus.running)
    db.commit()

    summary = build_review_report_summary(db, task.id)
    report = generate_report_with_retry(
        db,
        task=task,
        run=run,
        summary=summary,
        force_new_version=True,
        generation_reason="after_review",
    )
    if report is not None:
        append_event(
            db,
            run_id=run.id,
            event_type="report.created",
            stage="generate_report",
            message=f"人工审核完成后已生成第 {report.version} 版报告。",
            payload={
                "version": report.version,
                "generation_reason": "after_review",
                "sources_created": summary.sources_created,
                "evidence_created": summary.evidence_created,
                "included_claims": len(load_included_claim_ids(db, task.id)),
            },
        )
        db.commit()
    return report


def load_included_claim_ids(db: Session, task_id: str) -> list[str]:
    return [
        claim_id
        for (claim_id,) in db.execute(
            select(models.Claim.id).where(models.Claim.task_id == task_id, models.Claim.include_in_report.is_(True))
        ).all()
    ]


def verify_claims(db: Session, *, task: models.ResearchTask) -> dict[str, int | float]:
    claims = (
        db.execute(
            select(models.Claim)
            .where(models.Claim.task_id == task.id)
            .options(selectinload(models.Claim.evidence_links))
            .order_by(models.Claim.created_at.asc())
        )
        .scalars()
        .all()
    )

    claims_without_evidence = 0
    low_confidence_claims = 0
    conflict_claims = 0
    cited_claims = 0
    for claim in claims:
        if claim.evidence_links:
            cited_claims += 1
            claim.evidence_coverage = max(claim.evidence_coverage, 1.0)
        else:
            claims_without_evidence += 1
            claim.status = models.ClaimStatus.needs_evidence.value
            claim.confidence = "low"
            claim.confidence_score = min(claim.confidence_score, 0.4)
            claim.evidence_coverage = 0.0

        if claim.confidence_score < 0.55:
            low_confidence_claims += 1
            if claim.status == models.ClaimStatus.verified.value:
                claim.status = models.ClaimStatus.low_confidence.value

        if claim.status == models.ClaimStatus.conflict.value:
            conflict_claims += 1

    db.commit()
    citation_coverage = round(cited_claims / len(claims), 4) if claims else 0.0
    return {
        "claims_created": len(claims),
        "cited_claims": cited_claims,
        "claims_without_evidence": claims_without_evidence,
        "low_confidence_claims": low_confidence_claims,
        "conflict_claims": conflict_claims,
        "citation_coverage": citation_coverage,
    }


def mark_run_failed(db: Session, run_id: str, message: str) -> models.TaskRun:
    run = db.get(models.TaskRun, run_id)
    if run is None:
        raise ValueError("run_not_found")
    task = db.get(models.ResearchTask, run.task_id)
    run.status = models.RunStatus.failed.value
    run.current_stage = "failed"
    run.error_message = message
    run.finished_at = models.utc_now()
    if task:
        transition_task(task, models.TaskStatus.failed, reason=message)
    append_event(db, run_id=run.id, event_type="run.failed", stage="failed", message=message)
    db.commit()
    db.refresh(run)
    return run


def cancel_research_task(db: Session, task_id: str, *, reason: str = "canceled by user") -> models.TaskRun:
    task = db.get(models.ResearchTask, task_id)
    if task is None:
        raise ValueError("task_not_found")
    if task.status == models.TaskStatus.completed.value:
        raise ValueError("task_not_cancelable")

    latest_run = get_latest_run(db, task_id)
    if latest_run is None:
        raise ValueError("task_run_not_found")

    if latest_run.status != models.RunStatus.canceled.value:
        latest_run.status = models.RunStatus.canceled.value
        latest_run.current_stage = "canceled"
        latest_run.error_message = reason
        latest_run.finished_at = models.utc_now()

    if task.status != models.TaskStatus.canceled.value:
        transition_task(task, models.TaskStatus.canceled, reason=reason)
    task.failure_reason = reason

    append_event(db, run_id=latest_run.id, event_type="run.canceled", stage="canceled", message=reason, payload={"reason": reason})
    db.commit()
    db.refresh(latest_run)
    return latest_run


def get_unresolved_risky_claims(db: Session, task_id: str) -> list[models.Claim]:
    risky_claims = (
        db.execute(
            select(models.Claim)
            .where(models.Claim.task_id == task_id, models.Claim.status.in_(RISKY_CLAIM_STATUSES))
            .options(selectinload(models.Claim.review_decisions))
        )
        .scalars()
        .all()
    )
    unresolved: list[models.Claim] = []
    for claim in risky_claims:
        latest_review = max(claim.review_decisions, key=lambda item: item.created_at, default=None)
        if latest_review is None or latest_review.decision == "continue_research":
            unresolved.append(claim)
    return unresolved


def sync_task_review_status(db: Session, task_id: str) -> None:
    task = db.get(models.ResearchTask, task_id)
    if task is None:
        return

    if get_unresolved_risky_claims(db, task_id):
        return

    latest_run = get_latest_run(db, task_id)
    if latest_run:
        regenerate_report_after_review(db, task=task, run=latest_run)
    transition_task(task, models.TaskStatus.completed)
    if latest_run:
        latest_run.status = models.RunStatus.completed.value
        latest_run.current_stage = "completed"
        latest_run.finished_at = latest_run.finished_at or models.utc_now()
        append_event(db, run_id=latest_run.id, event_type="task.completed", stage="completed", message="风险结论已完成审阅，报告可以交付。")
    db.commit()


def record_review_decision_event(db: Session, claim: models.Claim, decision: models.ReviewDecision) -> None:
    task = db.get(models.ResearchTask, claim.task_id)
    latest_run = get_latest_run(db, claim.task_id)
    if latest_run is None:
        return

    payload = {
        "claim_id": claim.id,
        "decision": decision.decision,
        "resulting_status": decision.resulting_status,
        "reviewed_by": decision.reviewed_by,
    }
    append_event(
        db,
        run_id=latest_run.id,
        event_type="review.decision_created",
        stage="review_gate",
        message=f"Claim {claim.id} 已提交审阅决策：{decision.decision}",
        payload=payload,
    )
    if task and task.status == models.TaskStatus.completed.value:
        append_event(
            db,
            run_id=latest_run.id,
            event_type="task.completed",
            stage="completed",
            message="风险结论已完成审阅，报告可以交付。",
        )


def is_deep_research_task(task: models.ResearchTask) -> bool:
    scope = decode_json(task.scope_json)
    return scope.get("research_type") == DEEP_RESEARCH_TYPE or (not scope.get("competitors") and scope.get("template") == DEFAULT_DEEP_RESEARCH_TEMPLATE)


def write_demo_source_snapshot(db: Session, task_id: str, source_id: str, title: str, quote: str) -> None:
    """Demo 数据同样统一走 ArtifactStorage 写快照，保证离线模式下证据溯源链路可用。"""
    snapshot_html = (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>{escape_html(title)}</title></head>"
        f"<body><article><h1>{escape_html(title)}</h1><p>{escape_html(quote)}</p></article></body></html>"
    )
    snapshot_bytes = snapshot_html.encode("utf-8")
    object_key = f"snapshots/{task_id}/{source_id}.html"
    storage = build_artifact_storage(get_settings())
    storage.put_bytes(object_key, snapshot_bytes, content_type="text/html; charset=utf-8")
    db.add(
        models.SourceArtifact(
            source_id=source_id,
            artifact_type="html_snapshot",
            object_key=object_key,
            sha256=hashlib.sha256(snapshot_bytes).hexdigest(),
            content_type="text/html; charset=utf-8",
            size_bytes=len(snapshot_bytes),
        )
    )


def seed_generic_demo_research_objects(db: Session, task: models.ResearchTask) -> None:
    scope = decode_json(task.scope_json)
    research_question = str(scope.get("research_question") or task.title).strip()
    source_rows = [
        {
            "url": "https://example.com/rag-framework-evaluation",
            "source_type": "docs",
            "title": "RAG Framework Evaluation Guide",
            "publisher": "Example Research",
            "quote": f"RAG framework selection should start from the research question: {research_question}. Teams compare retrieval quality, integration fit, and evidence traceability before choosing a stack.",
            "quality": 0.82,
        },
        {
            "url": "https://example.com/rag-operations-risk",
            "source_type": "report",
            "title": "Enterprise RAG Operations Risk",
            "publisher": "Example Advisory",
            "quote": "Enterprise RAG deployments need monitoring for stale sources, embedding drift, access control gaps, and answer-level citation coverage.",
            "quality": 0.76,
        },
        {
            "url": "https://example.com/source-governance-checklist",
            "source_type": "docs",
            "title": "Source Governance Checklist",
            "publisher": "Example Knowledge Base",
            "quote": "A governed knowledge-base research workflow records source origin, retrieval time, document version, and claim-to-evidence links for every report conclusion.",
            "quality": 0.79,
        },
    ]

    evidence_by_title: dict[str, models.Evidence] = {}
    for row in source_rows:
        content_hash = hashlib.sha256(row["quote"].encode("utf-8")).hexdigest()
        source = models.Source(
            task_id=task.id,
            url=row["url"],
            canonical_url=row["url"],
            source_type=row["source_type"],
            title=row["title"],
            publisher=row["publisher"],
            content_hash=content_hash,
            is_primary=row["source_type"] in {"docs", "report"},
        )
        db.add(source)
        db.flush()
        write_demo_source_snapshot(db, task.id, source.id, row["title"], row["quote"])
        evidence_hash = hashlib.sha256(f"{source.id}:{row['quote']}".encode("utf-8")).hexdigest()
        evidence = models.Evidence(
            source_id=source.id,
            quote=row["quote"],
            locator_json=encode_json({"kind": "html", "heading": row["title"], "char_start": 0, "char_end": len(row["quote"])}),
            evidence_hash=evidence_hash,
            extraction_method="generic_demo_seed",
            source_version=1,
            language="en",
            quality_score=row["quality"],
        )
        db.add(evidence)
        db.flush()
        evidence_by_title[row["title"]] = evidence

    claims = [
        models.Claim(
            task_id=task.id,
            subject="RAG framework evaluation",
            predicate="requires_selection_criteria",
            value_json=encode_json({"criteria": ["retrieval_quality", "integration_fit", "evidence_traceability"]}),
            claim_type="methodology",
            dimension="architecture fit",
            status=models.ClaimStatus.verified.value,
            confidence="high",
            confidence_score=0.82,
            evidence_coverage=1.0,
            display_text=f"RAG framework evaluation should define selection criteria around the question: {research_question}.",
        ),
        models.Claim(
            task_id=task.id,
            subject="Operational risk",
            predicate="requires_monitoring",
            value_json=encode_json({"risks": ["stale_sources", "embedding_drift", "access_control_gaps", "citation_coverage"]}),
            claim_type="risk",
            dimension="operational risk",
            status=models.ClaimStatus.verified.value,
            confidence="medium",
            confidence_score=0.76,
            evidence_coverage=1.0,
            display_text="Enterprise RAG deployments need monitoring for stale sources, embedding drift, access control gaps, and citation coverage.",
        ),
        models.Claim(
            task_id=task.id,
            subject="Source governance",
            predicate="requires_traceability",
            value_json=encode_json({"traceability": ["source_origin", "retrieval_time", "document_version", "claim_evidence_links"]}),
            claim_type="governance",
            dimension="source governance",
            status=models.ClaimStatus.verified.value,
            confidence="medium",
            confidence_score=0.79,
            evidence_coverage=1.0,
            display_text="A governed deep research workflow records source origin, retrieval time, document version, and claim-to-evidence links.",
        ),
    ]
    db.add_all(claims)
    db.flush()

    db.add_all(
        [
            models.ClaimEvidence(claim_id=claims[0].id, evidence_id=evidence_by_title["RAG Framework Evaluation Guide"].id, relation="supports", weight=1.0),
            models.ClaimEvidence(claim_id=claims[1].id, evidence_id=evidence_by_title["Enterprise RAG Operations Risk"].id, relation="supports", weight=1.0),
            models.ClaimEvidence(claim_id=claims[2].id, evidence_id=evidence_by_title["Source Governance Checklist"].id, relation="supports", weight=1.0),
        ]
    )
    db.flush()

    report_snapshot = {
        **scope,
        "report_generation": {
            "reason": "initial_workflow",
            "template_version": "generic-demo-seed-v1",
            "included_claim_ids": [claim.id for claim in claims],
            "included_claim_count": len(claims),
            "risk_claim_count": sum(1 for claim in claims if claim.status in RISKY_CLAIM_STATUSES),
            "section_evidence": build_section_evidence_snapshots(claims),
        },
    }

    report = models.Report(
        task_id=task.id,
        version=1,
        status="draft",
        citation_coverage=1.0,
        input_snapshot_json=encode_json(report_snapshot),
        generated_at=models.utc_now(),
    )
    db.add(report)
    db.flush()
    db.add_all(
        [
            models.ReportSection(
                report_id=report.id,
                section_type="executive_summary",
                title="Executive Summary",
                content_markdown=f"This generic deep research draft is grounded in {len(source_rows)} seed sources and {len(claims)} traceable claims for: {research_question}.",
                order_no=1,
            ),
            models.ReportSection(
                report_id=report.id,
                section_type="key_claims",
                title="Key Claims",
                content_markdown="\n".join(f"- {claim.display_text}" for claim in claims),
                order_no=2,
            ),
        ]
    )
    db.commit()


def seed_demo_research_objects(db: Session, task_id: str) -> None:
    existing = db.execute(select(models.Source.id).where(models.Source.task_id == task_id)).first()
    if existing:
        return

    task = db.get(models.ResearchTask, task_id)
    if task is not None and is_deep_research_task(task):
        seed_generic_demo_research_objects(db, task)
        return

    source_rows = [
        {
            "url": "https://cursor.com/pricing",
            "source_type": "official",
            "title": "Cursor Pricing",
            "publisher": "Cursor",
            "quote": "Business plan includes privacy mode, admin controls, centralized billing and team management.",
            "quality": 0.88,
        },
        {
            "url": "https://docs.github.com/copilot",
            "source_type": "docs",
            "title": "GitHub Copilot Business Docs",
            "publisher": "GitHub Docs",
            "quote": "Copilot Business provides organization-level policies, seat management and enterprise controls.",
            "quality": 0.86,
        },
        {
            "url": "https://example.com/ai-coding-assistants-market-update",
            "source_type": "news",
            "title": "AI coding assistants market update",
            "publisher": "Example Tech News",
            "quote": "The market is shifting from single completion tools to agentic coding environments.",
            "quality": 0.62,
        },
    ]

    evidence_by_title: dict[str, models.Evidence] = {}
    for row in source_rows:
        content_hash = hashlib.sha256(row["quote"].encode("utf-8")).hexdigest()
        source = models.Source(
            task_id=task_id,
            url=row["url"],
            canonical_url=row["url"],
            source_type=row["source_type"],
            title=row["title"],
            publisher=row["publisher"],
            content_hash=content_hash,
            is_primary=row["source_type"] in {"official", "docs"},
        )
        db.add(source)
        db.flush()
        write_demo_source_snapshot(db, task_id, source.id, row["title"], row["quote"])
        evidence_hash = hashlib.sha256(f"{source.id}:{row['quote']}".encode("utf-8")).hexdigest()
        evidence = models.Evidence(
            source_id=source.id,
            quote=row["quote"],
            locator_json=encode_json({"kind": "html", "heading": row["title"], "char_start": 0, "char_end": len(row["quote"])}),
            evidence_hash=evidence_hash,
            extraction_method="demo_seed",
            source_version=1,
            language="en",
            quality_score=row["quality"],
        )
        db.add(evidence)
        db.flush()
        evidence_by_title[row["title"]] = evidence

    claims = [
        models.Claim(
            task_id=task_id,
            subject="Cursor",
            predicate="supports_feature",
            value_json=encode_json({"feature": "privacy_mode", "plan": "business"}),
            claim_type="feature_support",
            dimension="技术能力",
            status=models.ClaimStatus.verified.value,
            confidence="high",
            confidence_score=0.87,
            evidence_coverage=1.0,
            display_text="Cursor 在企业协作和隐私控制上更成熟。",
        ),
        models.Claim(
            task_id=task_id,
            subject="Trae",
            predicate="has_public_price",
            value_json=encode_json({"plan": "enterprise", "public_price": None}),
            claim_type="pricing",
            dimension="定价策略",
            status=models.ClaimStatus.undisclosed.value,
            confidence="medium",
            confidence_score=0.64,
            evidence_coverage=0.5,
            display_text="Trae 的企业版价格未公开披露。",
        ),
        models.Claim(
            task_id=task_id,
            subject="Windsurf",
            predicate="has_conflicting_price",
            value_json=encode_json({"plan": "pro", "conflict": True}),
            claim_type="pricing",
            dimension="定价策略",
            status=models.ClaimStatus.conflict.value,
            confidence="conflict",
            confidence_score=0.48,
            evidence_coverage=0.5,
            display_text="Windsurf Pro 套餐价格存在来源冲突。",
        ),
    ]
    db.add_all(claims)
    db.flush()

    db.add_all(
        [
            models.ClaimEvidence(claim_id=claims[0].id, evidence_id=evidence_by_title["Cursor Pricing"].id, relation="supports", weight=1.0),
            models.ClaimEvidence(claim_id=claims[0].id, evidence_id=evidence_by_title["GitHub Copilot Business Docs"].id, relation="supports", weight=0.6),
            models.ClaimEvidence(claim_id=claims[1].id, evidence_id=evidence_by_title["AI coding assistants market update"].id, relation="context", weight=0.5),
            models.ClaimEvidence(claim_id=claims[2].id, evidence_id=evidence_by_title["AI coding assistants market update"].id, relation="conflicts", weight=0.5),
        ]
    )
    db.flush()

    task = db.get(models.ResearchTask, task_id)
    report_snapshot = {
        **decode_json(task.scope_json if task else "{}"),
        "report_generation": {
            "reason": "initial_workflow",
            "template_version": "demo-seed-v1",
            "included_claim_ids": [claim.id for claim in claims],
            "included_claim_count": len(claims),
            "risk_claim_count": sum(1 for claim in claims if claim.status in RISKY_CLAIM_STATUSES),
            "section_evidence": build_section_evidence_snapshots(claims),
        },
    }

    report = models.Report(
        task_id=task_id,
        version=1,
        status="draft",
        citation_coverage=0.94,
        input_snapshot_json=encode_json(report_snapshot),
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
                content_markdown=(
                    "Cursor 在企业协作和隐私控制方面证据更充分 [S1]。"
                    "Trae 企业版公开定价暂未检索到可验证来源，应标记为未披露。"
                ),
                order_no=1,
            ),
            models.ReportSection(
                report_id=report.id,
                section_type="comparison",
                title="竞品对比",
                content_markdown=(
                    "| 产品 | 结论 | 状态 |\n"
                    "|---|---|---|\n"
                    "| Cursor | 企业控制能力较成熟 | 已验证 |\n"
                    "| Trae | 企业版价格未公开 | 未披露 |\n"
                    "| Windsurf | Pro 定价存在冲突 | 待审阅 |\n"
                ),
                order_no=2,
            ),
        ]
    )
    db.commit()


def serialize_task(task: models.ResearchTask) -> ResearchTaskOut:
    return ResearchTaskOut(
        id=task.id,
        title=task.title,
        prompt=task.prompt,
        scope=decode_json(task.scope_json),
        status=task.status,
        workspace_id=task.workspace_id,
        current_run_id=task.current_run_id,
        failure_reason=task.failure_reason,
        created_by=task.created_by,
        confirmed_at=task.confirmed_at,
        queued_at=task.queued_at,
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def serialize_run(run: models.TaskRun) -> TaskRunOut:
    return TaskRunOut(
        id=run.id,
        task_id=run.task_id,
        status=run.status,
        current_stage=run.current_stage,
        iteration_count=run.iteration_count,
        priority=run.priority,
        input_snapshot=decode_json(run.input_snapshot_json),
        error_message=run.error_message,
        queued_at=run.queued_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def serialize_event(event: models.ResearchEvent) -> ResearchEventOut:
    return ResearchEventOut(
        id=event.id,
        run_id=event.run_id,
        sequence_no=event.sequence_no,
        type=event.type,
        stage=event.stage,
        message=event.message,
        payload=decode_json(event.payload_json),
        severity=event.severity,
        actor=event.actor,
        created_at=event.created_at,
    )


def serialize_source(source: models.Source) -> SourceOut:
    return SourceOut(
        id=source.id,
        task_id=source.task_id,
        url=source.url,
        canonical_url=source.canonical_url,
        source_type=source.source_type,
        title=source.title,
        publisher=source.publisher,
        published_at=source.published_at,
        social_platform=source.social_platform,
        sentiment=source.sentiment,
        heat_score=source.heat_score,
        interaction_metrics=decode_json(source.interaction_metrics_json),
        retrieved_at=source.retrieved_at,
        content_hash=source.content_hash,
        index_status=source.index_status,
        is_primary=source.is_primary,
    )


def serialize_evidence(evidence: models.Evidence) -> EvidenceOut:
    locator = decode_json(evidence.locator_json)
    return EvidenceOut(
        id=evidence.id,
        source_id=evidence.source_id,
        quote=evidence.quote,
        locator=locator,
        social_metadata=locator.get("social", {}) if isinstance(locator.get("social"), dict) else {},
        evidence_hash=evidence.evidence_hash,
        extraction_method=evidence.extraction_method,
        source_version=evidence.source_version,
        language=evidence.language,
        quality_score=evidence.quality_score,
        source=serialize_source(evidence.source) if evidence.source else None,
    )


def decode_source_urls(value: str | None) -> list[dict[str, str]]:
    raw = json.loads(value or "[]")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def create_competitor_profile(db: Session, payload: CompetitorProfileCreate) -> CompetitorProfileOut:
    workspace_id = payload.workspace_id.strip() or DEFAULT_WORKSPACE_ID
    name = payload.name.strip()
    existing = (
        db.execute(
            select(models.CompetitorProfile).where(
                models.CompetitorProfile.workspace_id == workspace_id,
                models.CompetitorProfile.name == name,
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        raise ValueError("competitor_profile_exists")

    profile = models.CompetitorProfile(
        workspace_id=workspace_id,
        name=name,
        category=payload.category.strip() or "general",
        description=payload.description.strip(),
        homepage_url=payload.homepage_url.strip(),
        source_urls_json=encode_json([item.model_dump() for item in payload.source_urls]),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return serialize_competitor_profile(db, profile)


def list_competitor_profiles(db: Session, *, workspace_id: str = DEFAULT_WORKSPACE_ID) -> list[CompetitorProfileOut]:
    profiles = (
        db.execute(
            select(models.CompetitorProfile)
            .where(models.CompetitorProfile.workspace_id == workspace_id)
            .order_by(models.CompetitorProfile.name.asc())
        )
        .scalars()
        .all()
    )
    return [serialize_competitor_profile(db, profile) for profile in profiles]


def serialize_competitor_profile(db: Session, profile: models.CompetitorProfile) -> CompetitorProfileOut:
    source_urls = [CompetitorSourceUrl(**item) for item in decode_source_urls(profile.source_urls_json)]
    task_ids = matching_task_ids_for_competitor(db, profile.name)
    verified_claim_count = len(
        db.execute(
            select(models.Claim.id).where(
                models.Claim.subject == profile.name,
                models.Claim.status == models.ClaimStatus.verified.value,
            )
        ).all()
    )
    risky_claim_count = len(
        db.execute(
            select(models.Claim.id).where(
                models.Claim.subject == profile.name,
                models.Claim.status.in_(RISKY_CLAIM_STATUSES),
            )
        ).all()
    )
    report_count = 0
    if task_ids:
        report_count = len(db.execute(select(models.Report.id).where(models.Report.task_id.in_(task_ids))).all())
    return CompetitorProfileOut(
        id=profile.id,
        workspace_id=profile.workspace_id,
        name=profile.name,
        category=profile.category,
        description=profile.description,
        homepage_url=profile.homepage_url,
        source_urls=source_urls,
        source_count=len(source_urls),
        task_count=len(task_ids),
        verified_claim_count=verified_claim_count,
        risky_claim_count=risky_claim_count,
        report_count=report_count,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def matching_task_ids_for_competitor(db: Session, competitor_name: str) -> list[str]:
    name = competitor_name.strip().lower()
    matched: list[str] = []
    tasks = db.execute(select(models.ResearchTask.id, models.ResearchTask.scope_json)).all()
    for task_id, scope_json in tasks:
        competitors = decode_json(scope_json).get("competitors", [])
        if any(str(item).strip().lower() == name for item in competitors):
            matched.append(task_id)
    return matched


def get_source_snapshot(db: Session, source_id: str) -> SourceSnapshotOut | None:
    source = (
        db.execute(
            select(models.Source)
            .where(models.Source.id == source_id)
            .options(selectinload(models.Source.artifacts))
        )
        .scalars()
        .first()
    )
    if source is None:
        return None

    artifact = next((item for item in source.artifacts if item.artifact_type == "html_snapshot"), None)
    if artifact is None:
        return unavailable_source_snapshot(source_id, content_hash=source.content_hash, object_key=None)

    storage = build_artifact_storage(get_settings())
    try:
        html = storage.read_text(artifact.object_key)
    except (FileNotFoundError, ValueError):
        return unavailable_source_snapshot(source_id, content_hash=artifact.sha256, object_key=artifact.object_key)
    except httpx.HTTPStatusError:
        return unavailable_source_snapshot(source_id, content_hash=artifact.sha256, object_key=artifact.object_key)
    parsed = parse_html(html, prefer_trafilatura=False)
    summary_parts = [source.title, parsed.text]
    summary = "\n\n".join(part.strip() for part in summary_parts if part and part.strip())
    return SourceSnapshotOut(
        source_id=source_id,
        artifact_type=artifact.artifact_type,
        available=True,
        content_hash=artifact.sha256,
        object_key=artifact.object_key,
        summary=summary[:1200],
        char_count=len(html),
    )


def unavailable_source_snapshot(source_id: str, *, content_hash: str | None, object_key: str | None) -> SourceSnapshotOut:
    return SourceSnapshotOut(
        source_id=source_id,
        artifact_type="html_snapshot",
        available=False,
        content_hash=content_hash,
        object_key=object_key,
        summary="",
        char_count=0,
    )


def read_source_snapshot_raw(db: Session, source_id: str) -> tuple[str, models.SourceArtifact | None, bytes | None]:
    """读取来源快照原始字节。

    返回 (status, artifact, data)：
    - ("source_not_found", None, None)：来源不存在
    - ("snapshot_not_found", None, None)：来源存在但没有快照 artifact 记录
    - ("file_missing", artifact, None)：有记录但存储中文件缺失
    - ("ok", artifact, data)：正常读取
    """
    source = (
        db.execute(
            select(models.Source)
            .where(models.Source.id == source_id)
            .options(selectinload(models.Source.artifacts))
        )
        .scalars()
        .first()
    )
    if source is None:
        return "source_not_found", None, None

    artifact = next((item for item in source.artifacts if item.artifact_type == "html_snapshot"), None)
    if artifact is None:
        return "snapshot_not_found", None, None

    storage = build_artifact_storage(get_settings())
    try:
        data = storage.read_bytes(artifact.object_key)
    except (FileNotFoundError, ValueError):
        return "file_missing", artifact, None
    except httpx.HTTPStatusError:
        return "file_missing", artifact, None
    return "ok", artifact, data


def serialize_claim(claim: models.Claim) -> ClaimOut:
    latest_review = max(claim.review_decisions, key=lambda item: item.created_at, default=None)
    return ClaimOut(
        id=claim.id,
        task_id=claim.task_id,
        subject=claim.subject,
        predicate=claim.predicate,
        value=decode_json(claim.value_json),
        claim_type=claim.claim_type,
        dimension=claim.dimension,
        status=claim.status,
        confidence=claim.confidence,
        confidence_score=claim.confidence_score,
        display_text=claim.display_text,
        include_in_report=claim.include_in_report,
        evidence_coverage=claim.evidence_coverage,
        evidence_ids=[link.evidence_id for link in claim.evidence_links],
        review_decision=latest_review.decision if latest_review else None,
        review_reason=latest_review.reason if latest_review else None,
        reviewed_at=latest_review.created_at if latest_review else None,
    )


def serialize_report_section(section: models.ReportSection, section_evidence: list[dict]) -> ReportSectionOut:
    return ReportSectionOut(
        id=section.id,
        section_type=section.section_type,
        title=section.title,
        content_markdown=section.content_markdown,
        order_no=section.order_no,
        evidence=[ReportSectionEvidenceOut(**item) for item in section_evidence],
    )


def serialize_report_out(report: models.Report) -> ReportOut:
    input_snapshot = decode_json(report.input_snapshot_json)
    report_generation = input_snapshot.get("report_generation", {})
    section_evidence = report_generation.get("section_evidence", {}) if isinstance(report_generation, dict) else {}
    if not isinstance(section_evidence, dict):
        section_evidence = {}
    return ReportOut(
        id=report.id,
        task_id=report.task_id,
        version=report.version,
        status=report.status,
        citation_coverage=report.citation_coverage,
        input_snapshot=input_snapshot,
        generated_at=report.generated_at,
        created_at=report.created_at,
        sections=[
            serialize_report_section(section, section_evidence.get(section.section_type, []))
            for section in sorted(report.sections, key=lambda item: item.order_no)
        ],
    )


def serialize_report(report: models.Report) -> ReportOut:
    return serialize_report_out(report)


def regenerate_report_manually(db: Session, *, task: models.ResearchTask, run: models.TaskRun) -> models.Report | None:
    run.status = models.RunStatus.running.value
    run.current_stage = "generate_report"
    run.finished_at = None
    if task.status != models.TaskStatus.completed.value:
        transition_task(task, models.TaskStatus.running)
    db.commit()

    summary = build_review_report_summary(db, task.id)
    report = generate_report_with_retry(
        db,
        task=task,
        run=run,
        summary=summary,
        force_new_version=True,
        generation_reason="manual_regenerate",
    )
    if report is not None:
        append_event(
            db,
            run_id=run.id,
            event_type="report.created",
            stage="generate_report",
            message=f"已手动重新生成第 {report.version} 版报告。",
            payload={
                "version": report.version,
                "generation_reason": "manual_regenerate",
                "sources_created": summary.sources_created,
                "evidence_created": summary.evidence_created,
                "included_claims": len(load_included_claim_ids(db, task.id)),
            },
        )

    transition_task(task, models.TaskStatus.completed)
    run.status = models.RunStatus.completed.value
    run.current_stage = "completed"
    run.finished_at = models.utc_now()
    append_event(db, run_id=run.id, event_type="task.completed", stage="completed", message="报告已重新生成。")
    db.commit()
    if report is not None:
        db.refresh(report)
    return report


def get_task_detail(
    db: Session,
    task_id: str,
    *,
    evidence_competitor: str | None = None,
    evidence_dimension: str | None = None,
    evidence_source_type: str | None = None,
) -> TaskDetailOut | None:
    task = db.execute(
        select(models.ResearchTask)
        .where(models.ResearchTask.id == task_id)
        .options(
            selectinload(models.ResearchTask.runs),
            selectinload(models.ResearchTask.sources),
            selectinload(models.ResearchTask.claims).selectinload(models.Claim.evidence_links),
            selectinload(models.ResearchTask.claims).selectinload(models.Claim.review_decisions),
            selectinload(models.ResearchTask.reports).selectinload(models.Report.sections),
        )
    ).scalar_one_or_none()
    if task is None:
        return None

    evidence_statement = select(models.Evidence).join(models.Source).where(models.Source.task_id == task_id)
    source_type = evidence_source_type.strip() if evidence_source_type else ""
    competitor = evidence_competitor.strip() if evidence_competitor else ""
    dimension = evidence_dimension.strip() if evidence_dimension else ""
    if source_type:
        evidence_statement = evidence_statement.where(models.Source.source_type.ilike(source_type))
    if competitor or dimension:
        evidence_statement = evidence_statement.join(models.ClaimEvidence).join(models.Claim)
        evidence_statement = evidence_statement.where(models.Claim.task_id == task_id)
    if competitor:
        evidence_statement = evidence_statement.where(models.Claim.subject.ilike(competitor))
    if dimension:
        evidence_statement = evidence_statement.where(or_(models.Claim.dimension.ilike(dimension), models.Claim.claim_type.ilike(dimension)))
    evidence = db.execute(evidence_statement.distinct().options(selectinload(models.Evidence.source))).scalars().all()
    sorted_runs = sorted(task.runs, key=lambda item: item.started_at or item.queued_at or datetime.min, reverse=True)
    return TaskDetailOut(
        task=serialize_task(task),
        latest_run=serialize_run(sorted_runs[0]) if sorted_runs else None,
        runs=[serialize_run(run) for run in sorted_runs],
        sources=[serialize_source(source) for source in task.sources],
        evidence=[serialize_evidence(item) for item in evidence],
        claims=[serialize_claim(claim) for claim in task.claims],
        reports=[serialize_report_out(report) for report in sorted(task.reports, key=lambda item: item.version)],
    )


def build_monitoring_metrics(db: Session) -> dict[str, Any]:
    settings = get_settings()
    counts = {
        "research_tasks": db.execute(select(func.count()).select_from(models.ResearchTask)).scalar_one(),
        "task_runs": db.execute(select(func.count()).select_from(models.TaskRun)).scalar_one(),
        "research_events": db.execute(select(func.count()).select_from(models.ResearchEvent)).scalar_one(),
        "sources": db.execute(select(func.count()).select_from(models.Source)).scalar_one(),
        "evidence": db.execute(select(func.count()).select_from(models.Evidence)).scalar_one(),
        "claims": db.execute(select(func.count()).select_from(models.Claim)).scalar_one(),
        "reports": db.execute(select(func.count()).select_from(models.Report)).scalar_one(),
        "review_decisions": db.execute(select(func.count()).select_from(models.ReviewDecision)).scalar_one(),
        "source_artifacts": db.execute(select(func.count()).select_from(models.SourceArtifact)).scalar_one(),
    }
    return {
        "environment": settings.environment,
        "task_mode": settings.task_mode,
        "database_backend": settings.database_url.split("://", 1)[0],
        "counts": counts,
        "latest_run_started_at": db.execute(select(func.max(models.TaskRun.started_at))).scalar_one(),
        "latest_run_finished_at": db.execute(select(func.max(models.TaskRun.finished_at))).scalar_one(),
        "latest_event_at": db.execute(select(func.max(models.ResearchEvent.created_at))).scalar_one(),
    }
