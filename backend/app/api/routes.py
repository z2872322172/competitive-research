import json
from hashlib import sha256
from time import sleep

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.config import get_settings
from app.db import SessionLocal, get_db
from app.schemas import (
    CancelTaskCreate,
    ClaimOut,
    CompetitorProfileCreate,
    CompetitorProfileOut,
    MonitoringMetricsOut,
    ResearchEventOut,
    ResearchTaskCreate,
    ResearchTaskOut,
    ReportOut,
    SearchHitOut,
    SearchIndexRebuildOut,
    ReviewDecisionCreate,
    ReviewDecisionOut,
    SourceSnapshotOut,
    TaskDetailOut,
    TaskRunOut,
)
from app.services import report_export
from app.services import research_service
from app.services.storage.artifacts import build_artifact_storage
from app.services.search.indexing import ElasticsearchIndexer
from app.services.search.retrieval import search_research_index

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/worker/health")
def worker_health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "configured",
        "task_mode": settings.task_mode,
        "broker": settings.celery_broker_url,
        "result_backend": settings.celery_result_backend,
        "registered_task": "research.run",
    }


@router.get("/metrics", response_model=MonitoringMetricsOut)
def monitoring_metrics(db: Session = Depends(get_db)) -> MonitoringMetricsOut:
    return MonitoringMetricsOut(**research_service.build_monitoring_metrics(db))


@router.post("/research-tasks/{task_id}/search-index/rebuild", response_model=SearchIndexRebuildOut)
def rebuild_research_task_search_index(
    task_id: str,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    created_by: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> SearchIndexRebuildOut:
    task = db.get(models.ResearchTask, task_id)
    if task is None or not task_matches_scope(task.workspace_id, task.created_by, workspace_id, created_by):
        raise HTTPException(status_code=404, detail="research task not found")
    summary = ElasticsearchIndexer(get_settings()).rebuild_task(db, task_id)
    return SearchIndexRebuildOut(
        task_id=task_id,
        sources_indexed=summary.sources_indexed,
        evidence_indexed=summary.evidence_indexed,
        failed_sources=summary.failed_sources,
        index_backend="elasticsearch",
    )


@router.get("/search", response_model=list[SearchHitOut])
def search_research_sources(
    q: str = "",
    task_id: str | None = None,
    competitor: str | None = None,
    dimension: str | None = None,
    source_type: str | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[SearchHitOut]:
    if task_id is not None and db.get(models.ResearchTask, task_id) is None:
        raise HTTPException(status_code=404, detail="research task not found")
    hits = search_research_index(
        db,
        get_settings(),
        query=q,
        task_id=task_id,
        competitor=competitor,
        dimension=dimension,
        source_type=source_type,
        limit=limit,
    )
    return [SearchHitOut(**hit.__dict__) for hit in hits]


@router.post("/competitors", response_model=CompetitorProfileOut, status_code=201)
def create_competitor_profile(payload: CompetitorProfileCreate, db: Session = Depends(get_db)) -> CompetitorProfileOut:
    try:
        return research_service.create_competitor_profile(db, payload)
    except ValueError as exc:
        if str(exc) == "competitor_profile_exists":
            raise HTTPException(status_code=409, detail={"code": "competitor_profile_exists", "message": "competitor profile already exists"}) from exc
        raise


@router.get("/competitors", response_model=list[CompetitorProfileOut])
def list_competitor_profiles(workspace_id: str = "default", db: Session = Depends(get_db)) -> list[CompetitorProfileOut]:
    return research_service.list_competitor_profiles(db, workspace_id=workspace_id)


@router.post("/research-tasks", response_model=ResearchTaskOut, status_code=201)
def create_research_task(payload: ResearchTaskCreate, db: Session = Depends(get_db)) -> ResearchTaskOut:
    task = research_service.create_task(db, payload)
    return research_service.serialize_task(task)


@router.get("/research-tasks", response_model=list[ResearchTaskOut])
def list_research_tasks(
    *,
    status: str | None = None,
    q: str | None = None,
    workspace_id: str | None = None,
    created_by: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[ResearchTaskOut]:
    statement = select(models.ResearchTask)
    if status:
        statement = statement.where(models.ResearchTask.status == status)
    if workspace_id:
        statement = statement.where(models.ResearchTask.workspace_id == workspace_id)
    if created_by:
        statement = statement.where(models.ResearchTask.created_by == created_by)
    if q:
        keyword = f"%{q}%"
        statement = statement.where(models.ResearchTask.title.ilike(keyword) | models.ResearchTask.prompt.ilike(keyword))
    tasks = db.execute(statement.order_by(models.ResearchTask.created_at.desc()).offset(skip).limit(limit)).scalars().all()
    return [research_service.serialize_task(task) for task in tasks]


@router.get("/research-tasks/{task_id}", response_model=TaskDetailOut)
def get_research_task(
    task_id: str,
    evidence_competitor: str | None = None,
    evidence_dimension: str | None = None,
    evidence_source_type: str | None = None,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    created_by: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> TaskDetailOut:
    detail = research_service.get_task_detail(
        db,
        task_id,
        evidence_competitor=evidence_competitor,
        evidence_dimension=evidence_dimension,
        evidence_source_type=evidence_source_type,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="research task not found")
    if not task_matches_scope(detail.task.workspace_id, detail.task.created_by, workspace_id, created_by):
        raise HTTPException(status_code=404, detail="research task not found")
    return detail


def enqueue_research_run(run: models.TaskRun, *, resume: bool = False) -> None:
    from app.workers.tasks import run_research_task

    kwargs = {"resume": True} if resume else None
    run_research_task.apply_async(args=[run.id], kwargs=kwargs, queue="research", priority=run.priority)


def run_workflow_in_background(run_id: str, resume: bool = False) -> None:
    from app.workflows.research_graph import run_research_workflow

    db = SessionLocal()
    try:
        run_research_workflow(db, run_id, delay_seconds=0.2, resume=resume)
    except Exception as exc:
        research_service.mark_run_failed(db, run_id, str(exc))
    finally:
        db.close()


def task_matches_scope(
    resource_workspace_id: str,
    resource_created_by: str,
    workspace_id: str | None,
    created_by: str | None,
) -> bool:
    if workspace_id and resource_workspace_id != workspace_id:
        return False
    if created_by and resource_created_by != created_by:
        return False
    return True


@router.post("/research-tasks/{task_id}/confirm", response_model=TaskRunOut)
def confirm_research_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    priority: int = Query(default=5, ge=0, le=9),
    background: bool = Query(default=False),
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    created_by: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> TaskRunOut:
    task = db.get(models.ResearchTask, task_id)
    if task is None or not task_matches_scope(task.workspace_id, task.created_by, workspace_id, created_by):
        raise HTTPException(status_code=404, detail="research task not found")
    try:
        run = research_service.create_run(db, task_id, priority=priority)
    except ValueError as exc:
        raise task_error(exc) from exc

    if get_settings().task_mode == "celery":
        enqueue_research_run(run)
        db.refresh(run)
        return research_service.serialize_run(run)

    if background:
        background_tasks.add_task(run_workflow_in_background, run.id)
        db.refresh(run)
        return research_service.serialize_run(run)

    try:
        run = research_service.simulate_research_run(db, run.id)
    except Exception as exc:
        run = research_service.mark_run_failed(db, run.id, str(exc))
        raise HTTPException(status_code=500, detail={"code": "task_run_failed", "message": run.error_message or "research run failed"}) from exc
    return research_service.serialize_run(run)


@router.post("/research-tasks/{task_id}/runs", response_model=TaskRunOut, status_code=201)
def rerun_research_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    priority: int = Query(default=5, ge=0, le=9),
    background: bool = Query(default=False),
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    created_by: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> TaskRunOut:
    task = db.get(models.ResearchTask, task_id)
    if task is None or not task_matches_scope(task.workspace_id, task.created_by, workspace_id, created_by):
        raise HTTPException(status_code=404, detail="research task not found")
    try:
        run = research_service.create_run(db, task_id, allow_rerun=True, priority=priority)
    except ValueError as exc:
        raise task_error(exc) from exc

    if get_settings().task_mode == "celery":
        enqueue_research_run(run)
        db.refresh(run)
        return research_service.serialize_run(run)

    if background:
        background_tasks.add_task(run_workflow_in_background, run.id)
        db.refresh(run)
        return research_service.serialize_run(run)

    try:
        run = research_service.simulate_research_run(db, run.id)
    except Exception as exc:
        run = research_service.mark_run_failed(db, run.id, str(exc))
        raise HTTPException(status_code=500, detail={"code": "task_run_failed", "message": run.error_message or "research run failed"}) from exc
    return research_service.serialize_run(run)


@router.post("/research-tasks/{task_id}/resume", response_model=TaskRunOut)
def resume_research_task(
    task_id: str,
    background_tasks: BackgroundTasks,
    background: bool = Query(default=False),
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    created_by: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> TaskRunOut:
    task = db.get(models.ResearchTask, task_id)
    if task is None or not task_matches_scope(task.workspace_id, task.created_by, workspace_id, created_by):
        raise HTTPException(status_code=404, detail="research task not found")
    try:
        run = research_service.prepare_failed_run_resume(db, task_id)
    except ValueError as exc:
        raise task_error(exc) from exc

    if get_settings().task_mode == "celery":
        enqueue_research_run(run, resume=True)
        db.refresh(run)
        return research_service.serialize_run(run)

    if background:
        background_tasks.add_task(run_workflow_in_background, run.id, True)
        db.refresh(run)
        return research_service.serialize_run(run)

    try:
        from app.workflows.research_graph import run_research_workflow

        run = run_research_workflow(db, run.id, resume=True)
    except Exception as exc:
        db.refresh(run)
        raise HTTPException(
            status_code=500,
            detail={"code": "task_resume_failed", "message": run.error_message or str(exc) or "research resume failed"},
        ) from exc
    return research_service.serialize_run(run)


@router.post("/research-tasks/{task_id}/cancel", response_model=TaskRunOut)
def cancel_research_task(
    task_id: str,
    payload: CancelTaskCreate,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    created_by: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> TaskRunOut:
    task = db.get(models.ResearchTask, task_id)
    if task is None or not task_matches_scope(task.workspace_id, task.created_by, workspace_id, created_by):
        raise HTTPException(status_code=404, detail="research task not found")
    try:
        run = research_service.cancel_research_task(db, task_id, reason=payload.reason)
    except ValueError as exc:
        raise task_error(exc) from exc
    return research_service.serialize_run(run)


@router.delete("/dev/demo-data")
def reset_demo_data(db: Session = Depends(get_db)) -> dict[str, int | str]:
    if get_settings().environment not in {"dev", "development", "local", "test"}:
        raise HTTPException(status_code=403, detail={"code": "dev_only", "message": "demo data reset is only available in development"})

    task_count = db.execute(select(models.ResearchTask.id)).all()
    for model in [
        models.CompetitorProfile,
        models.ReviewDecision,
        models.ClaimEvidence,
        models.ReportSection,
        models.Report,
        models.Evidence,
        models.SourceArtifact,
        models.Source,
        models.ResearchEvent,
        models.TaskRun,
        models.Claim,
        models.ResearchTask,
    ]:
        db.execute(delete(model))
    db.commit()
    return {"status": "ok", "deleted_tasks": len(task_count)}


@router.get("/research-tasks/{task_id}/events", response_model=list[ResearchEventOut])
def list_research_events(task_id: str, after: int = 0, db: Session = Depends(get_db)) -> list[ResearchEventOut]:
    task = db.get(models.ResearchTask, task_id)
    run = None
    if task and task.current_run_id:
        current_run = db.get(models.TaskRun, task.current_run_id)
        if current_run and current_run.task_id == task_id:
            run = current_run
    if run is None:
        run = (
            db.execute(
                select(models.TaskRun)
                .where(models.TaskRun.task_id == task_id)
                .order_by(models.TaskRun.queued_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
    if run is None:
        return []
    events = (
        db.execute(
            select(models.ResearchEvent)
            .where(models.ResearchEvent.run_id == run.id, models.ResearchEvent.sequence_no > after)
            .order_by(models.ResearchEvent.sequence_no.asc())
        )
        .scalars()
        .all()
    )
    return [research_service.serialize_event(event) for event in events]


@router.get("/research-tasks/{task_id}/events/stream")
def stream_research_events(task_id: str, after: int = 0, db: Session = Depends(get_db)) -> StreamingResponse:
    def event_generator():
        cursor = after
        idle_ticks = 0
        while idle_ticks < 60:
            events = list_research_events(task_id, cursor, db)
            if not events:
                idle_ticks += 1
                sleep(1)
                continue
            idle_ticks = 0
            for event in events:
                cursor = event.sequence_no
                yield f"id: {event.sequence_no}\nevent: {event.type}\ndata: {event.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/sources/{source_id}")
def get_source(source_id: str, db: Session = Depends(get_db)):
    source = db.get(models.Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    return source


@router.get("/sources/{source_id}/snapshot", response_model=SourceSnapshotOut)
def get_source_snapshot(source_id: str, db: Session = Depends(get_db)) -> SourceSnapshotOut:
    snapshot = research_service.get_source_snapshot(db, source_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="source not found")
    return snapshot


@router.get("/sources/{source_id}/snapshot/raw")
def get_source_snapshot_raw(source_id: str, db: Session = Depends(get_db)) -> Response:
    status, artifact, data = research_service.read_source_snapshot_raw(db, source_id)
    if status in {"source_not_found", "snapshot_not_found"}:
        raise HTTPException(status_code=404, detail={"code": f"{status}", "message": "snapshot not found for this source"})
    if status == "file_missing" or data is None or artifact is None:
        raise HTTPException(status_code=404, detail={"code": "snapshot_file_missing", "message": "snapshot file is not available in artifact storage"})
    return Response(
        content=data,
        media_type=artifact.content_type or "text/html; charset=utf-8",
        headers={
            "X-Artifact-Object-Key": artifact.object_key,
            "X-Artifact-Sha256": artifact.sha256 or "",
            "X-Artifact-Size": str(len(data)),
        },
    )


@router.get("/evidence/{evidence_id}")
def get_evidence(evidence_id: str, db: Session = Depends(get_db)):
    evidence = (
        db.execute(
            select(models.Evidence)
            .where(models.Evidence.id == evidence_id)
            .options(selectinload(models.Evidence.source))
        )
        .scalars()
        .first()
    )
    if evidence is None:
        raise HTTPException(status_code=404, detail="evidence not found")
    return research_service.serialize_evidence(evidence)


@router.get("/claims/{claim_id}", response_model=ClaimOut)
def get_claim(
    claim_id: str,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    created_by: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> ClaimOut:
    claim = (
        db.execute(
            select(models.Claim)
            .where(models.Claim.id == claim_id)
            .options(
                selectinload(models.Claim.task),
                selectinload(models.Claim.evidence_links),
                selectinload(models.Claim.review_decisions),
            )
        )
        .scalars()
        .first()
    )
    if claim is None:
        raise HTTPException(status_code=404, detail="claim not found")
    if not task_matches_scope(claim.task.workspace_id, claim.task.created_by, workspace_id, created_by):
        raise HTTPException(status_code=404, detail="claim not found")
    return research_service.serialize_claim(claim)


@router.post("/claims/{claim_id}/review", response_model=ReviewDecisionOut, status_code=201)
def review_claim(
    claim_id: str,
    payload: ReviewDecisionCreate,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    created_by: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> ReviewDecisionOut:
    claim = (
        db.execute(
            select(models.Claim)
            .where(models.Claim.id == claim_id)
            .options(selectinload(models.Claim.task))
        )
        .scalars()
        .first()
    )
    if claim is None:
        raise HTTPException(status_code=404, detail="claim not found")
    if not task_matches_scope(claim.task.workspace_id, claim.task.created_by, workspace_id, created_by):
        raise HTTPException(status_code=404, detail="claim not found")

    previous_status = claim.status
    resulting_status = previous_status
    if payload.decision == "accept":
        claim.status = models.ClaimStatus.verified.value
        claim.include_in_report = True
        resulting_status = claim.status
    if payload.decision == "exclude":
        claim.include_in_report = False
        resulting_status = claim.status
    if payload.decision == "mark_uncertain":
        claim.status = models.ClaimStatus.low_confidence.value
        claim.confidence = "low"
        resulting_status = claim.status
    decision = models.ReviewDecision(
        claim_id=claim_id,
        decision=payload.decision,
        reason=payload.reason,
        previous_status=previous_status,
        resulting_status=resulting_status,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    research_service.record_review_decision_event(db, claim, decision)
    research_service.sync_task_review_status(db, claim.task_id)
    return decision


@router.post("/research-tasks/{task_id}/reports/regenerate", response_model=ReportOut, status_code=201)
def regenerate_task_report(
    task_id: str,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    created_by: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> ReportOut:
    task = (
        db.execute(
            select(models.ResearchTask)
            .where(models.ResearchTask.id == task_id)
            .options(selectinload(models.ResearchTask.reports), selectinload(models.ResearchTask.runs))
        )
        .scalars()
        .first()
    )
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    if not task_matches_scope(task.workspace_id, task.created_by, workspace_id, created_by):
        raise HTTPException(status_code=404, detail="task not found")
    if not task.reports:
        raise HTTPException(status_code=409, detail="report regeneration requires an existing report")

    unresolved = research_service.get_unresolved_risky_claims(db, task_id)
    if unresolved:
        raise HTTPException(status_code=409, detail="unresolved risky claims remain")

    latest_run = research_service.get_latest_run(db, task_id)
    if latest_run is None:
        raise HTTPException(status_code=409, detail="report regeneration requires a task run")

    report = research_service.regenerate_report_manually(db, task=task, run=latest_run)
    if report is None:
        raise HTTPException(status_code=500, detail="report regeneration failed")
    return research_service.serialize_report_out(report)


@router.get("/reports/{report_id}")
def get_report(
    report_id: str,
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    created_by: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
):
    report = (
        db.execute(
            select(models.Report)
            .where(models.Report.id == report_id)
            .options(selectinload(models.Report.task), selectinload(models.Report.sections))
        )
        .scalars()
        .first()
    )
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    if not task_matches_scope(report.task.workspace_id, report.task.created_by, workspace_id, created_by):
        raise HTTPException(status_code=404, detail="report not found")
    return report


@router.post("/reports/{report_id}/export")
def export_report(
    report_id: str,
    format: str = "markdown",
    workspace_id: str | None = Header(default=None, alias="X-Workspace-Id"),
    created_by: str | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
):
    report = (
        db.execute(
            select(models.Report)
            .where(models.Report.id == report_id)
            .options(selectinload(models.Report.task), selectinload(models.Report.sections))
        )
        .scalars()
        .first()
    )
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    if not task_matches_scope(report.task.workspace_id, report.task.created_by, workspace_id, created_by):
        raise HTTPException(status_code=404, detail="report not found")
    report_out = research_service.serialize_report_out(report)
    normalized_format = report_export.normalize_export_format(format)
    if normalized_format == "markdown":
        artifact = report_export.render_report_export(
            report_out,
            format=normalized_format,
            report_title=report.task.title if report.task else None,
        )
        storage = build_artifact_storage(get_settings())
        stored = storage.put_bytes(artifact.object_key or report_export.build_report_export_object_key(report_out, format=normalized_format), artifact.content, content_type=artifact.content_type)
        existing_artifact = (
            db.execute(
                select(models.ReportArtifact).where(
                    models.ReportArtifact.report_id == report.id,
                    models.ReportArtifact.artifact_type == normalized_format,
                )
            )
            .scalars()
            .first()
        )
        if existing_artifact is None:
            existing_artifact = models.ReportArtifact(report_id=report.id, artifact_type=normalized_format, object_key=stored.object_key, sha256=sha256(artifact.content).hexdigest(), content_type=artifact.content_type, size_bytes=len(artifact.content))
            db.add(existing_artifact)
        else:
            existing_artifact.object_key = stored.object_key
            existing_artifact.sha256 = sha256(artifact.content).hexdigest()
            existing_artifact.content_type = artifact.content_type
            existing_artifact.size_bytes = len(artifact.content)
        db.commit()
        return JSONResponse(
            content={"format": "markdown", "content": artifact.content.decode("utf-8")},
            headers={"X-Artifact-Object-Key": stored.object_key},
        )
    else:
        try:
            artifact = report_export.render_report_export(
                report_out,
                format=normalized_format,
                report_title=report.task.title if report.task else None,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail={"code": "unsupported_export_format", "message": str(exc) or "unsupported export format"},
            ) from exc

    storage = build_artifact_storage(get_settings())
    stored = storage.put_bytes(artifact.object_key or report_export.build_report_export_object_key(report_out, format=normalized_format), artifact.content, content_type=artifact.content_type)
    existing_artifact = (
        db.execute(
            select(models.ReportArtifact).where(
                models.ReportArtifact.report_id == report.id,
                models.ReportArtifact.artifact_type == normalized_format,
            )
        )
        .scalars()
        .first()
    )
    if existing_artifact is None:
        db.add(
            models.ReportArtifact(
                report_id=report.id,
                artifact_type=normalized_format,
                object_key=stored.object_key,
                sha256=sha256(artifact.content).hexdigest(),
                content_type=artifact.content_type,
                size_bytes=len(artifact.content),
            )
        )
    else:
        existing_artifact.object_key = stored.object_key
        existing_artifact.sha256 = sha256(artifact.content).hexdigest()
        existing_artifact.content_type = artifact.content_type
        existing_artifact.size_bytes = len(artifact.content)
    db.commit()

    return Response(
        content=artifact.content,
        media_type=artifact.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.filename}"',
            "X-Artifact-Object-Key": stored.object_key,
        },
    )


def task_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    if code == "task_not_found":
        return HTTPException(status_code=404, detail={"code": code, "message": "research task not found"})
    if code.startswith("invalid_task_transition"):
        return HTTPException(status_code=409, detail={"code": "invalid_task_transition", "message": code})
    if code in {"task_already_running", "task_not_confirmable", "task_not_cancelable", "task_run_not_found", "task_not_resumable", "resume_checkpoint_not_found"}:
        messages = {
            "task_already_running": "research task already has an active run",
            "task_not_confirmable": "only draft research tasks can be confirmed; use rerun endpoint for existing tasks",
            "task_not_cancelable": "completed research tasks cannot be canceled",
            "task_run_not_found": "research task has no run to cancel",
            "task_not_resumable": "only failed research runs can be resumed from a checkpoint",
            "resume_checkpoint_not_found": "research task has no successful checkpoint to resume from",
        }
        return HTTPException(status_code=409, detail={"code": code, "message": messages[code]})
    return HTTPException(status_code=400, detail={"code": code, "message": code})
