from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.config import Settings
from app.services.search.indexing import decode_scope


@dataclass(frozen=True)
class SearchHit:
    id: str
    kind: str
    score: float
    task_id: str
    source_id: str | None
    title: str
    snippet: str
    source_type: str | None
    publisher: str | None
    source_url: str | None
    competitors: list[str]
    dimensions: list[str]
    created_at: datetime | None


class ElasticsearchSearcher:
    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.elasticsearch_url.rstrip("/")
        self.timeout_seconds = 5.0
        self.source_index = "verda-sources"
        self.evidence_index = "verda-evidence"

    def search(
        self,
        *,
        query: str = "",
        task_id: str | None = None,
        competitor: str | None = None,
        dimension: str | None = None,
        source_type: str | None = None,
        limit: int = 20,
    ) -> list[SearchHit]:
        body = self._build_query(
            query=query,
            task_id=task_id,
            competitor=competitor,
            dimension=dimension,
            source_type=source_type,
            limit=limit,
        )
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(f"{self.base_url}/verda-sources,verda-evidence/_search", json=body)
            response.raise_for_status()
            payload = response.json()
        return [self._parse_hit(hit) for hit in payload.get("hits", {}).get("hits", []) if isinstance(hit, dict)]

    def _build_query(
        self,
        *,
        query: str,
        task_id: str | None,
        competitor: str | None,
        dimension: str | None,
        source_type: str | None,
        limit: int,
    ) -> dict[str, Any]:
        filters: list[dict[str, Any]] = []
        if task_id:
            filters.append({"term": {"task_id": task_id}})
        if competitor:
            filters.append({"term": {"competitors": competitor}})
        if dimension:
            filters.append({"term": {"dimensions": dimension}})
        if source_type:
            filters.append({"term": {"source_type": source_type}})

        if query.strip():
            must_clause: dict[str, Any] = {
                "multi_match": {
                    "query": query.strip(),
                    "fields": ["title^3", "quote^4", "source_title^2", "publisher", "url", "canonical_url"],
                }
            }
        else:
            must_clause = {"match_all": {}}

        return {"size": limit, "query": {"bool": {"must": [must_clause], "filter": filters}}}

    def _parse_hit(self, hit: dict[str, Any]) -> SearchHit:
        source = hit.get("_source", {})
        if not isinstance(source, dict):
            source = {}
        kind = "evidence" if "evidence_id" in source else "source"
        return SearchHit(
            id=str(source.get("evidence_id") or source.get("source_id") or hit.get("_id") or ""),
            kind=kind,
            score=float(hit.get("_score") or 0.0),
            task_id=str(source.get("task_id") or ""),
            source_id=str(source.get("source_id")) if source.get("source_id") else None,
            title=str(source.get("title") or source.get("source_title") or ""),
            snippet=str(source.get("quote") or source.get("canonical_url") or source.get("url") or ""),
            source_type=str(source.get("source_type")) if source.get("source_type") else None,
            publisher=str(source.get("publisher")) if source.get("publisher") else None,
            source_url=str(source.get("source_url") or source.get("url")) if (source.get("source_url") or source.get("url")) else None,
            competitors=[str(item) for item in source.get("competitors", []) if str(item).strip()]
            if isinstance(source.get("competitors"), list)
            else [],
            dimensions=[str(item) for item in source.get("dimensions", []) if str(item).strip()]
            if isinstance(source.get("dimensions"), list)
            else [],
            created_at=_parse_datetime(source.get("created_at")),
        )


def search_research_index(
    db: Session,
    settings: Settings,
    *,
    query: str = "",
    task_id: str | None = None,
    competitor: str | None = None,
    dimension: str | None = None,
    source_type: str | None = None,
    limit: int = 20,
) -> list[SearchHit]:
    try:
        return ElasticsearchSearcher(settings).search(
            query=query,
            task_id=task_id,
            competitor=competitor,
            dimension=dimension,
            source_type=source_type,
            limit=limit,
        )
    except Exception:
        return search_research_db(
            db,
            query=query,
            task_id=task_id,
            competitor=competitor,
            dimension=dimension,
            source_type=source_type,
            limit=limit,
        )


def search_research_db(
    db: Session,
    *,
    query: str = "",
    task_id: str | None = None,
    competitor: str | None = None,
    dimension: str | None = None,
    source_type: str | None = None,
    limit: int = 20,
) -> list[SearchHit]:
    sources = (
        db.execute(
            select(models.Source)
            .options(selectinload(models.Source.evidence_items), selectinload(models.Source.task))
            .order_by(models.Source.retrieved_at.desc())
        )
        .scalars()
        .all()
    )
    normalized_query = query.strip().lower()
    results: list[SearchHit] = []
    for source in sources:
        if task_id and source.task_id != task_id:
            continue
        if source_type and source.source_type != source_type:
            continue
        task = source.task
        scope = decode_scope(task.scope_json if task else None)
        if competitor and competitor not in scope["competitors"]:
            continue
        if dimension and dimension not in scope["dimensions"]:
            continue

        source_score = score_text(
            normalized_query,
            " ".join([source.title, source.publisher, source.canonical_url, source.url]).lower(),
            base_score=0.65 if source.is_primary else 0.5,
        )
        if source_score > 0:
            results.append(
                SearchHit(
                    id=source.id,
                    kind="source",
                    score=source_score,
                    task_id=source.task_id,
                    source_id=source.id,
                    title=source.title,
                    snippet=source.canonical_url or source.url,
                    source_type=source.source_type,
                    publisher=source.publisher,
                    source_url=source.canonical_url or source.url,
                    competitors=scope["competitors"],
                    dimensions=scope["dimensions"],
                    created_at=source.retrieved_at,
                )
            )

        for evidence in source.evidence_items:
            evidence_score = score_text(
                normalized_query,
                " ".join([evidence.quote, source.title, source.publisher]).lower(),
                base_score=evidence.quality_score,
            )
            if evidence_score <= 0:
                continue
            results.append(
                SearchHit(
                    id=evidence.id,
                    kind="evidence",
                    score=evidence_score,
                    task_id=source.task_id,
                    source_id=source.id,
                    title=source.title,
                    snippet=evidence.quote,
                    source_type=source.source_type,
                    publisher=source.publisher,
                    source_url=source.canonical_url or source.url,
                    competitors=scope["competitors"],
                    dimensions=scope["dimensions"],
                    created_at=evidence.created_at,
                )
            )

    results.sort(key=lambda item: item.score, reverse=True)
    return results[:limit]


def score_text(query: str, haystack: str, *, base_score: float) -> float:
    if not query:
        return base_score
    score = base_score
    tokens = [token for token in query.split() if token]
    matches = sum(1 for token in tokens if token in haystack)
    if matches == 0:
        return 0.0
    return min(1.0, score + (matches / max(len(tokens), 1)) * 0.4)


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None
