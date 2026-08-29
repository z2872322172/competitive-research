"""来源/快照/证据端点（共用工作区隔离校验）。"""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.api.deps import ensure_source_accessible
from app.auth import AuthContext, get_auth
from app.db import get_db
from app.schemas import SourceSnapshotOut
from app.services import research_service

router = APIRouter()


@router.get("/sources/{source_id}")
def get_source(source_id: int, auth: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    source = ensure_source_accessible(db, db.get(models.Source, source_id), auth)
    return source


@router.get("/sources/{source_id}/snapshot", response_model=SourceSnapshotOut)
def get_source_snapshot(
    source_id: int,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> SourceSnapshotOut:
    source = ensure_source_accessible(db, db.get(models.Source, source_id), auth)
    snapshot = research_service.get_source_snapshot(db, source.id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="source not found")
    return snapshot


@router.get("/sources/{source_id}/snapshot/raw")
def get_source_snapshot_raw(
    source_id: int,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> Response:
    source = db.get(models.Source, source_id)
    if source is not None:
        # 隔离校验只拦截"存在但无权访问"的来源；不存在的来源交给领域层返回 source_not_found 错误码。
        ensure_source_accessible(db, source, auth)
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
def get_evidence(
    evidence_id: int,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
):
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
    ensure_source_accessible(db, evidence.source, auth)
    return research_service.serialize_evidence(evidence)
