"""报告端点：报告详情、手动重新生成与多格式导出。"""

from hashlib import sha256

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.auth import AuthContext, get_auth
from app.config import get_settings
from app.db import get_db
from app.schemas import ReportOut
from app.services import report_export, research_service
from app.services.storage.artifacts import build_artifact_storage

router = APIRouter()


@router.post("/research-tasks/{task_id}/reports/regenerate", response_model=ReportOut, status_code=201)
def regenerate_task_report(
    task_id: int,
    auth: AuthContext = Depends(get_auth),
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
    if not auth.can_access(task.workspace_id, task.created_by):
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
    report_id: int,
    auth: AuthContext = Depends(get_auth),
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
    if not auth.can_access(report.task.workspace_id, report.task.created_by):
        raise HTTPException(status_code=404, detail="report not found")
    return report


@router.post("/reports/{report_id}/export")
def export_report(
    report_id: int,
    format: str = "markdown",
    auth: AuthContext = Depends(get_auth),
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
    if not auth.can_access(report.task.workspace_id, report.task.created_by):
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
