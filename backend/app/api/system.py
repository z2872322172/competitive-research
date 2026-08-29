"""系统级端点：健康检查、监控指标与演示数据重置。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models
from app.auth import AuthContext, require_auth
from app.config import get_settings
from app.db import get_db
from app.schemas import MonitoringMetricsOut
from app.services import research_service

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
def monitoring_metrics(
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
) -> MonitoringMetricsOut:
    return MonitoringMetricsOut(**research_service.build_monitoring_metrics(db))


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
