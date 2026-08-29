"""研究任务端点：澄清计划、任务 CRUD、确认/重跑/恢复/取消与事件流。"""

from time import sleep

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.api.deps import enqueue_research_run, run_workflow_in_background, task_error
from app.auth import AuthContext, get_auth
from app.config import get_settings
from app.db import get_db
from app.schemas import (
    CancelTaskCreate,
    ResearchClarifyRequest,
    ResearchEventOut,
    ResearchPlanSuggestionOut,
    ResearchTaskCreate,
    ResearchTaskOut,
    TaskDetailOut,
    TaskRunOut,
)
from app.services import research_planning, research_service

router = APIRouter()


@router.post("/research-plans/clarify", response_model=ResearchPlanSuggestionOut)
def clarify_research_plan(
    payload: ResearchClarifyRequest,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> ResearchPlanSuggestionOut:
    # 第一阶段使用可离线运行的动态规划器；规划器内部后续可替换为 LLM，不影响前端契约。
    auth.resolve_workspace_for_create(payload.workspace_id)
    return research_planning.build_clarification_plan(payload.prompt, settings=get_settings())


@router.post("/research-tasks", response_model=ResearchTaskOut, status_code=201)
def create_research_task(
    payload: ResearchTaskCreate,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> ResearchTaskOut:
    # strict 模式下任务归属与创建人由登录态决定，禁止客户端伪造他人工作区/署名。
    payload.workspace_id = auth.resolve_workspace_for_create(payload.workspace_id)
    if auth.strict:
        payload.created_by = auth.username
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
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> list[ResearchTaskOut]:
    statement = select(models.ResearchTask)
    if status:
        statement = statement.where(models.ResearchTask.status == status)
    if auth.strict:
        # 隔离边界：只返回登录用户所在工作区的任务，query 参数中的过滤词被忽略。
        visible_workspaces = [workspace_id] if workspace_id in auth.workspace_ids else auth.workspace_ids
        statement = statement.where(models.ResearchTask.workspace_id.in_(visible_workspaces))
    else:
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
    task_id: int,
    evidence_competitor: str | None = None,
    evidence_dimension: str | None = None,
    evidence_source_type: str | None = None,
    auth: AuthContext = Depends(get_auth),
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
    if not auth.can_access(detail.task.workspace_id, detail.task.created_by):
        raise HTTPException(status_code=404, detail="research task not found")
    return detail


@router.post("/research-tasks/{task_id}/confirm", response_model=TaskRunOut)
def confirm_research_task(
    task_id: int,
    background_tasks: BackgroundTasks,
    priority: int = Query(default=5, ge=0, le=9),
    background: bool = Query(default=False),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> TaskRunOut:
    task = db.get(models.ResearchTask, task_id)
    if task is None or not auth.can_access(task.workspace_id, task.created_by):
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
    task_id: int,
    background_tasks: BackgroundTasks,
    priority: int = Query(default=5, ge=0, le=9),
    background: bool = Query(default=False),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> TaskRunOut:
    task = db.get(models.ResearchTask, task_id)
    if task is None or not auth.can_access(task.workspace_id, task.created_by):
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
    task_id: int,
    background_tasks: BackgroundTasks,
    background: bool = Query(default=False),
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> TaskRunOut:
    task = db.get(models.ResearchTask, task_id)
    if task is None or not auth.can_access(task.workspace_id, task.created_by):
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
    task_id: int,
    payload: CancelTaskCreate,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> TaskRunOut:
    task = db.get(models.ResearchTask, task_id)
    if task is None or not auth.can_access(task.workspace_id, task.created_by):
        raise HTTPException(status_code=404, detail="research task not found")
    try:
        run = research_service.cancel_research_task(db, task_id, reason=payload.reason)
    except ValueError as exc:
        raise task_error(exc) from exc
    return research_service.serialize_run(run)


@router.get("/research-tasks/{task_id}/events", response_model=list[ResearchEventOut])
def list_research_events(
    task_id: int,
    after: int = 0,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> list[ResearchEventOut]:
    task = db.get(models.ResearchTask, task_id)
    if task is None or not auth.can_access(task.workspace_id, task.created_by):
        return []
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
def stream_research_events(
    task_id: int,
    after: int = 0,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    task = db.get(models.ResearchTask, task_id)
    if task is None or not auth.can_access(task.workspace_id, task.created_by):
        raise HTTPException(status_code=404, detail="research task not found")

    def event_generator():
        cursor = after
        idle_ticks = 0
        while idle_ticks < 60:
            events = list_research_events(task_id, cursor, auth=auth, db=db)
            if not events:
                idle_ticks += 1
                sleep(1)
                continue
            idle_ticks = 0
            for event in events:
                cursor = event.sequence_no
                yield f"id: {event.sequence_no}\nevent: {event.type}\ndata: {event.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
