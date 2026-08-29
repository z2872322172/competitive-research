"""路由层共享依赖：任务运行调度、来源隔离校验与错误码映射。"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.db import SessionLocal
from app.services import research_service


def enqueue_research_run(run: models.TaskRun, *, resume: bool = False) -> None:
    from app.workers.tasks import run_research_task

    kwargs = {"resume": True} if resume else None
    run_research_task.apply_async(args=[run.id], kwargs=kwargs, queue="research", priority=run.priority)


def run_workflow_in_background(run_id: int, resume: bool = False) -> None:
    from app.workflows.research_graph import run_research_workflow

    db = SessionLocal()
    try:
        run_research_workflow(db, run_id, delay_seconds=0.2, resume=resume)
    except Exception as exc:
        research_service.mark_run_failed(db, run_id, str(exc))
    finally:
        db.close()


def ensure_source_accessible(db: Session, source: models.Source | None, auth) -> models.Source:
    """来源/快照/证据共用的隔离校验：经所属任务判断工作区归属。"""
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    task = db.get(models.ResearchTask, source.task_id)
    if task is None or not auth.can_access(task.workspace_id, task.created_by):
        raise HTTPException(status_code=404, detail="source not found")
    return source


def task_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    if code == "task_not_found":
        return HTTPException(status_code=404, detail={"code": code, "message": "research task not found"})
    if code.startswith("invalid_task_transition"):
        return HTTPException(status_code=409, detail={"code": "invalid_task_transition", "message": code})
    if code.startswith("invalid_run_transition"):
        return HTTPException(status_code=409, detail={"code": "invalid_run_transition", "message": code})
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
