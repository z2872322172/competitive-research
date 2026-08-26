import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import models
from app.config import Settings


@dataclass(frozen=True)
class SearchIndexSyncSummary:
    sources_indexed: int = 0
    evidence_indexed: int = 0
    failed_sources: int = 0


class ElasticsearchIndexer:
    def __init__(self, settings: Settings) -> None:
        parsed = urlparse(settings.elasticsearch_url.rstrip("/"))
        self.base_url = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
        self.timeout_seconds = 5.0
        self.source_index = "verda-sources"
        self.evidence_index = "verda-evidence"

    def sync_source_bundle(self, db: Session, source: models.Source) -> SearchIndexSyncSummary:
        try:
            self.ensure_indices()
            task = db.get(models.ResearchTask, source.task_id)
            scope = decode_scope(task.scope_json if task else None)
            self.index_source(source, competitors=scope["competitors"], dimensions=scope["dimensions"])
            evidence_indexed = 0
            for evidence in source.evidence_items:
                self.index_evidence(source, evidence, competitors=scope["competitors"], dimensions=scope["dimensions"])
                evidence_indexed += 1

            source.index_status = "indexed"
            source.indexed_at = models.utc_now()
            db.commit()
            return SearchIndexSyncSummary(sources_indexed=1, evidence_indexed=evidence_indexed, failed_sources=0)
        except Exception:
            source.index_status = "failed"
            db.commit()
            return SearchIndexSyncSummary(sources_indexed=0, evidence_indexed=0, failed_sources=1)

    def rebuild_task(self, db: Session, task_id: int) -> SearchIndexSyncSummary:
        task = db.get(models.ResearchTask, task_id)
        scope = decode_scope(task.scope_json if task else None)
        sources = (
            db.execute(
                select(models.Source)
                .where(models.Source.task_id == task_id)
                .options(selectinload(models.Source.evidence_items))
                .order_by(models.Source.retrieved_at.asc())
            )
            .scalars()
            .all()
        )
        summary = SearchIndexSyncSummary()
        for source in sources:
            source_competitors = scope["competitors"]
            source_dimensions = scope["dimensions"]
            result = self.sync_source_bundle(db, source)
            summary = SearchIndexSyncSummary(
                sources_indexed=summary.sources_indexed + result.sources_indexed,
                evidence_indexed=summary.evidence_indexed + result.evidence_indexed,
                failed_sources=summary.failed_sources + result.failed_sources,
            )
        return summary

    def ensure_indices(self) -> None:
        for index_name, mapping in self._index_definitions().items():
            response = self._request("HEAD", f"/{index_name}", raise_for_status=False)
            if response.status_code == 404:
                self._request("PUT", f"/{index_name}", json={"mappings": mapping})

    def index_source(self, source: models.Source, *, competitors: list[str], dimensions: list[str]) -> None:
        self._request(
            "PUT",
            f"/{self.source_index}/_doc/{source.id}",
            json=build_source_index_document(source, competitors=competitors, dimensions=dimensions),
        )

    def index_evidence(
        self,
        source: models.Source,
        evidence: models.Evidence,
        *,
        competitors: list[str],
        dimensions: list[str],
    ) -> None:
        self._request(
            "PUT",
            f"/{self.evidence_index}/_doc/{evidence.id}",
            json=build_evidence_index_document(source, evidence, competitors=competitors, dimensions=dimensions),
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        raise_for_status: bool = True,
    ) -> httpx.Response:
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.request(method, f"{self.base_url}{path}", json=json)
            if raise_for_status and response.status_code >= 400:
                response.raise_for_status()
            return response

    def _index_definitions(self) -> dict[str, dict[str, Any]]:
        return {
            self.source_index: {
                "properties": {
                    "source_id": {"type": "keyword"},
                    "task_id": {"type": "keyword"},
                    "title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "url": {"type": "keyword"},
                    "canonical_url": {"type": "keyword"},
                    "source_type": {"type": "keyword"},
                    "publisher": {"type": "keyword"},
                    "social_platform": {"type": "keyword"},
                    "sentiment": {"type": "keyword"},
                    "heat_score": {"type": "float"},
                    "content_hash": {"type": "keyword"},
                    "index_status": {"type": "keyword"},
                    "is_primary": {"type": "boolean"},
                    "competitors": {"type": "keyword"},
                    "dimensions": {"type": "keyword"},
                    "retrieved_at": {"type": "date"},
                    "indexed_at": {"type": "date"},
                }
            },
            self.evidence_index: {
                "properties": {
                    "evidence_id": {"type": "keyword"},
                    "task_id": {"type": "keyword"},
                    "source_id": {"type": "keyword"},
                    "quote": {"type": "text"},
                    "evidence_hash": {"type": "keyword"},
                    "extraction_method": {"type": "keyword"},
                    "source_version": {"type": "integer"},
                    "language": {"type": "keyword"},
                    "quality_score": {"type": "float"},
                    "source_title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "source_url": {"type": "keyword"},
                    "source_type": {"type": "keyword"},
                    "publisher": {"type": "keyword"},
                    "competitors": {"type": "keyword"},
                    "dimensions": {"type": "keyword"},
                    "created_at": {"type": "date"},
                }
            },
        }


def decode_scope(scope_json: str | None) -> dict[str, list[str]]:
    try:
        payload = json.loads(scope_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    competitors = [str(item).strip() for item in payload.get("competitors", []) if str(item).strip()]
    dimensions = [str(item).strip() for item in payload.get("dimensions", []) if str(item).strip()]
    return {"competitors": competitors, "dimensions": dimensions}


def build_source_index_document(
    source: models.Source,
    *,
    competitors: list[str],
    dimensions: list[str],
) -> dict[str, Any]:
    return {
        "source_id": source.id,
        "task_id": source.task_id,
        "title": source.title,
        "url": source.url,
        "canonical_url": source.canonical_url,
        "source_type": source.source_type,
        "publisher": source.publisher,
        "social_platform": source.social_platform,
        "sentiment": source.sentiment,
        "heat_score": source.heat_score,
        "content_hash": source.content_hash,
        "index_status": source.index_status,
        "is_primary": source.is_primary,
        "competitors": competitors,
        "dimensions": dimensions,
        "retrieved_at": source.retrieved_at.isoformat() if source.retrieved_at else None,
        "indexed_at": source.indexed_at.isoformat() if source.indexed_at else None,
    }


def build_evidence_index_document(
    source: models.Source,
    evidence: models.Evidence,
    *,
    competitors: list[str],
    dimensions: list[str],
) -> dict[str, Any]:
    return {
        "evidence_id": evidence.id,
        "task_id": source.task_id,
        "source_id": source.id,
        "quote": evidence.quote,
        "evidence_hash": evidence.evidence_hash,
        "extraction_method": evidence.extraction_method,
        "source_version": evidence.source_version,
        "language": evidence.language,
        "quality_score": evidence.quality_score,
        "source_title": source.title,
        "source_url": source.canonical_url or source.url,
        "source_type": source.source_type,
        "publisher": source.publisher,
        "competitors": competitors,
        "dimensions": dimensions,
        "created_at": evidence.created_at.isoformat() if evidence.created_at else None,
    }
