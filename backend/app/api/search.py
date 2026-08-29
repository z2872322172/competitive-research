"""检索端点：全文检索与研究任务索引重建。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models
from app.auth import AuthContext, get_auth, require_auth
from app.config import get_settings
from app.db import get_db
from app.schemas import SearchHitOut, SearchIndexRebuildOut
from app.services.search.indexing import ElasticsearchIndexer
from app.services.search.retrieval import search_research_index

router = APIRouter()


@router.post("/research-tasks/{task_id}/search-index/rebuild", response_model=SearchIndexRebuildOut)
def rebuild_research_task_search_index(
    task_id: int,
    auth: AuthContext = Depends(get_auth),
    db: Session = Depends(get_db),
) -> SearchIndexRebuildOut:
    task = db.get(models.ResearchTask, task_id)
    if task is None or not auth.can_access(task.workspace_id, task.created_by):
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
    task_id: int | None = None,
    competitor: str | None = None,
    dimension: str | None = None,
    source_type: str | None = None,
    limit: int = Query(default=20, ge=1, le=50),
    auth: AuthContext = Depends(require_auth),
    db: Session = Depends(get_db),
) -> list[SearchHitOut]:
    task = db.get(models.ResearchTask, task_id) if task_id is not None else None
    if task_id is not None and (task is None or not auth.can_access(task.workspace_id, task.created_by)):
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
