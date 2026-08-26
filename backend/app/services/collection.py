import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.config import Settings, get_settings
from app.services.fetching.fetcher import FetchResult, HttpPageFetcher, WebFetchError, canonicalize_url
from app.services.fetching.rate_limit import DomainRateLimiter
from app.services.fetching.robots import RobotsPolicyChecker
from app.services.parsing.evidence_extractor import build_keywords, extract_evidence
from app.services.parsing.html_parser import ParsedPage, parse_html
from app.services.reporting import create_claim_report
from app.services.search.adapters import build_search_adapter, extract_urls
from app.services.search.indexing import ElasticsearchIndexer
from app.services.search.base import SearchProviderUnavailable, SearchResult
from app.services.social.adapters import build_public_social_metadata, build_social_listening_adapter, split_social_urls
from app.services.storage.artifacts import build_artifact_storage


EventWriter = Callable[[str, str, str, dict[str, Any] | None], None]


@dataclass
class CollectionSummary:
    provider: str
    searched: bool = False
    source_candidates: int = 0
    sources_created: int = 0
    evidence_created: int = 0
    skipped_urls: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    robots_blocked: int = 0
    low_quality_sources: int = 0


@dataclass
class SourceDiscovery:
    scope: dict[str, Any]
    query: str
    results: list[SearchResult]
    summary: CollectionSummary


@dataclass
class FetchedSource:
    result: SearchResult
    canonical_url: str
    fetched: FetchResult


@dataclass
class ParsedSource:
    result: SearchResult
    fetched: FetchResult
    parsed: ParsedPage
    source_id: int


def serialize_search_result(result: SearchResult) -> dict[str, Any]:
    return {
        "title": result.title,
        "url": result.url,
        "snippet": result.snippet,
        "score": result.score,
        "source_type": result.source_type,
        "metadata": result.metadata,
    }


def deserialize_search_result(data: dict[str, Any]) -> SearchResult:
    return SearchResult(
        title=str(data.get("title", "")),
        url=str(data.get("url", "")),
        snippet=str(data.get("snippet", "")),
        score=float(data.get("score", 0.5)),
        source_type=str(data.get("source_type", "web")),
        metadata=dict(data.get("metadata", {})) if isinstance(data.get("metadata"), dict) else {},
    )


def serialize_fetch_result(result: FetchResult) -> dict[str, Any]:
    return {
        "url": result.url,
        "final_url": result.final_url,
        "html": result.html,
        "content_type": result.content_type,
        "status_code": result.status_code,
    }


def deserialize_fetch_result(data: dict[str, Any]) -> FetchResult:
    return FetchResult(
        url=str(data.get("url", "")),
        final_url=str(data.get("final_url", "")),
        html=str(data.get("html", "")),
        content_type=str(data.get("content_type", "")),
        status_code=int(data.get("status_code", 0)),
    )


def serialize_parsed_page(page: ParsedPage) -> dict[str, Any]:
    return {
        "title": page.title,
        "text": page.text,
        "paragraphs": list(page.paragraphs),
        "parser_name": page.parser_name,
    }


def deserialize_parsed_page(data: dict[str, Any]) -> ParsedPage:
    paragraphs = data.get("paragraphs", [])
    if not isinstance(paragraphs, list):
        paragraphs = []
    return ParsedPage(
        title=str(data.get("title", "")),
        text=str(data.get("text", "")),
        paragraphs=[str(item) for item in paragraphs if str(item).strip()],
        parser_name=str(data.get("parser_name", "stdlib_html_parser")),
    )


def serialize_collection_summary(summary: CollectionSummary) -> dict[str, Any]:
    return {
        "provider": summary.provider,
        "searched": summary.searched,
        "source_candidates": summary.source_candidates,
        "sources_created": summary.sources_created,
        "evidence_created": summary.evidence_created,
        "skipped_urls": list(summary.skipped_urls),
        "errors": list(summary.errors),
        "robots_blocked": summary.robots_blocked,
        "low_quality_sources": summary.low_quality_sources,
    }


def deserialize_collection_summary(data: dict[str, Any]) -> CollectionSummary:
    return CollectionSummary(
        provider=str(data.get("provider", "unknown")),
        searched=bool(data.get("searched", False)),
        source_candidates=int(data.get("source_candidates", 0)),
        sources_created=int(data.get("sources_created", 0)),
        evidence_created=int(data.get("evidence_created", 0)),
        skipped_urls=[str(item) for item in data.get("skipped_urls", []) if str(item).strip()],
        errors=[str(item) for item in data.get("errors", []) if str(item).strip()],
        robots_blocked=int(data.get("robots_blocked", 0)),
        low_quality_sources=int(data.get("low_quality_sources", 0)),
    )


def serialize_source_discovery(discovery: SourceDiscovery) -> dict[str, Any]:
    return {
        "scope": discovery.scope,
        "query": discovery.query,
        "results": [serialize_search_result(item) for item in discovery.results],
        "summary": serialize_collection_summary(discovery.summary),
    }


def deserialize_source_discovery(data: dict[str, Any]) -> SourceDiscovery:
    summary_data = data.get("summary", {})
    if not isinstance(summary_data, dict):
        summary_data = {}
    results_data = data.get("results", [])
    if not isinstance(results_data, list):
        results_data = []
    return SourceDiscovery(
        scope=dict(data.get("scope", {})),
        query=str(data.get("query", "")),
        results=[deserialize_search_result(item) for item in results_data if isinstance(item, dict)],
        summary=deserialize_collection_summary(summary_data),
    )


def dedupe_search_results(results: list[SearchResult]) -> list[SearchResult]:
    deduped: list[SearchResult] = []
    seen_urls: set[str] = set()
    for result in results:
        canonical_url = canonicalize_url(result.url)
        if canonical_url in seen_urls:
            continue
        seen_urls.add(canonical_url)
        deduped.append(result)
    return deduped


def serialize_fetched_source(item: FetchedSource) -> dict[str, Any]:
    return {
        "result": serialize_search_result(item.result),
        "canonical_url": item.canonical_url,
        "fetched": serialize_fetch_result(item.fetched),
    }


def deserialize_fetched_source(data: dict[str, Any]) -> FetchedSource:
    fetched_data = data.get("fetched", {})
    if not isinstance(fetched_data, dict):
        fetched_data = {}
    result_data = data.get("result", {})
    if not isinstance(result_data, dict):
        result_data = {}
    return FetchedSource(
        result=deserialize_search_result(result_data),
        canonical_url=str(data.get("canonical_url", "")),
        fetched=deserialize_fetch_result(fetched_data),
    )


def serialize_parsed_source(item: ParsedSource) -> dict[str, Any]:
    return {
        "result": serialize_search_result(item.result),
        "fetched": serialize_fetch_result(item.fetched),
        "parsed": serialize_parsed_page(item.parsed),
        "source_id": item.source_id,
    }


def deserialize_parsed_source(data: dict[str, Any]) -> ParsedSource:
    fetched_data = data.get("fetched", {})
    parsed_data = data.get("parsed", {})
    result_data = data.get("result", {})
    if not isinstance(fetched_data, dict):
        fetched_data = {}
    if not isinstance(parsed_data, dict):
        parsed_data = {}
    if not isinstance(result_data, dict):
        result_data = {}
    return ParsedSource(
        result=deserialize_search_result(result_data),
        fetched=deserialize_fetch_result(fetched_data),
        parsed=deserialize_parsed_page(parsed_data),
        source_id=str(data.get("source_id", "")),
    )


def serialize_fetched_sources(items: list[FetchedSource]) -> list[dict[str, Any]]:
    return [serialize_fetched_source(item) for item in items]


def deserialize_fetched_sources(items: list[dict[str, Any]]) -> list[FetchedSource]:
    return [deserialize_fetched_source(item) for item in items if isinstance(item, dict)]


def serialize_parsed_sources(items: list[ParsedSource]) -> list[dict[str, Any]]:
    return [serialize_parsed_source(item) for item in items]


def deserialize_parsed_sources(items: list[dict[str, Any]]) -> list[ParsedSource]:
    return [deserialize_parsed_source(item) for item in items if isinstance(item, dict)]


def collect_research_evidence(
    db: Session,
    *,
    task: models.ResearchTask,
    run: models.TaskRun,
    settings: Settings,
    write_event: EventWriter,
) -> CollectionSummary:
    discovery = discover_research_sources(db, task=task, settings=settings, write_event=write_event)
    fetched_sources = fetch_research_sources(discovery=discovery, settings=settings, write_event=write_event)
    parsed_sources = parse_research_sources(
        db,
        task=task,
        discovery=discovery,
        fetched_sources=fetched_sources,
        settings=settings,
        write_event=write_event,
    )
    return extract_research_evidence(
        db,
        task=task,
        discovery=discovery,
        parsed_sources=parsed_sources,
        settings=settings,
        write_event=write_event,
    )


def discover_research_sources(
    db: Session,
    *,
    task: models.ResearchTask,
    settings: Settings,
    write_event: EventWriter,
    search_plan: dict[str, Any] | None = None,
) -> SourceDiscovery:
    scope = decode_json(task.scope_json)
    summary = CollectionSummary(provider=settings.search_provider)
    existing = db.execute(select(models.Source.id).where(models.Source.task_id == task.id)).first()
    if existing:
        return SourceDiscovery(scope=scope, query="", results=[], summary=summary)

    planned_preferences = search_plan.get("source_preferences") if search_plan else None
    source_preferences = planned_preferences if isinstance(planned_preferences, list) else scope.get("source_preferences")
    planned_social_sources = search_plan.get("social_source_urls") if search_plan else None
    candidate_urls = extract_urls(source_preferences, task.prompt, planned_social_sources)
    manual_urls, social_urls = split_social_urls(candidate_urls)

    planned_query = str(search_plan.get("query") or "").strip() if search_plan else ""
    query = planned_query or build_query(task.prompt, scope)
    planned_budget = search_plan.get("budget") if search_plan else None
    planned_limit = planned_budget.get("max_candidate_sources") if isinstance(planned_budget, dict) else None
    max_results = settings.search_max_results
    if isinstance(planned_limit, int) and planned_limit > 0:
        max_results = min(max_results, planned_limit)
    source_type_priority = search_plan.get("source_type_priority") if search_plan else None
    if not isinstance(source_type_priority, list) or not source_type_priority:
        source_type_priority = ["official", "docs", "news", "social", "web"]
    priority_map = {str(source_type).strip(): index for index, source_type in enumerate(source_type_priority) if str(source_type).strip()}

    adapter = None
    try:
        adapter = build_search_adapter(settings, manual_urls=manual_urls)
    except SearchProviderUnavailable as exc:
        summary.errors.append(str(exc))
        write_event(
            "search.skipped",
            "discover_sources",
            "未配置 Tavily API Key，真实搜索跳过；将回退到 demo 数据。",
            {"reason": str(exc)},
        )
        if not social_urls:
            return SourceDiscovery(scope=scope, query=query, results=[], summary=summary)

    write_event("search.started", "discover_sources", "开始使用 Tavily / URL 适配器检索真实来源。", {"query": query})
    results: list[SearchResult] = []
    if adapter is not None:
        results.extend(adapter.search(query, max_results=max_results))

    if social_urls:
        social_adapter = build_social_listening_adapter(settings, social_urls=social_urls)
        write_event("social.started", "discover_sources", "Start public social source normalization.", {"urls": social_urls})
        results.extend(social_adapter.search(query, max_results=max_results))

    results = dedupe_search_results(results)
    results = sorted(results, key=lambda item: priority_map.get(item.source_type, len(priority_map)))
    if len(results) > max_results:
        results = results[:max_results]
    summary.searched = True
    summary.source_candidates = len(results)
    write_event("source.found", "discover_sources", f"发现 {len(results)} 个候选来源。", {"urls": [item.url for item in results]})
    if not results:
        write_event(
            "source.search_exhausted",
            "discover_sources",
            "Search completed without any usable source candidates; downstream workflow will use its fallback path.",
            {
                "query": query,
                "candidate_count": 0,
            },
        )
    return SourceDiscovery(scope=scope, query=query, results=results, summary=summary)


def fetch_research_sources(
    *,
    discovery: SourceDiscovery,
    settings: Settings,
    write_event: EventWriter,
) -> list[FetchedSource]:
    if not discovery.results:
        return []

    fetcher = HttpPageFetcher(
        timeout_seconds=settings.fetch_timeout_seconds,
        user_agent=settings.fetch_user_agent,
        max_retries=settings.fetch_max_retries,
        retry_backoff_seconds=settings.fetch_retry_backoff_seconds,
        max_bytes=settings.fetch_max_bytes,
        rate_limiter=DomainRateLimiter(min_interval_seconds=settings.fetch_rate_limit_seconds),
        robots_policy=RobotsPolicyChecker(timeout_seconds=settings.fetch_timeout_seconds) if settings.fetch_respect_robots else None,
    )

    fetched_sources: list[FetchedSource] = []
    seen_urls: set[str] = set()
    for result in discovery.results:
        canonical_url = canonicalize_url(result.url)
        if canonical_url in seen_urls:
            discovery.summary.skipped_urls.append(canonical_url)
            continue
        seen_urls.add(canonical_url)

        try:
            fetched = fetcher.fetch(canonical_url)
        except (httpx.HTTPError, WebFetchError, ValueError) as exc:
            error = f"{canonical_url}:{exc}"
            discovery.summary.errors.append(error)
            if str(exc).startswith("robots_disallowed"):
                discovery.summary.robots_blocked += 1
            write_event("source.fetch_failed", "fetch_source", "来源抓取失败，已跳过。", {"url": canonical_url, "error": str(exc)})
            continue

        fetched_sources.append(FetchedSource(result=result, canonical_url=canonical_url, fetched=fetched))

    if discovery.results and not fetched_sources and discovery.summary.errors:
        write_event(
            "source.fetch_exhausted",
            "fetch_sources",
            "All discovered sources failed to fetch; downstream workflow will use its fallback path.",
            {
                "candidate_count": len(discovery.results),
                "failed_count": len(discovery.summary.errors),
            },
        )
    return fetched_sources


def parse_research_sources(
    db: Session,
    *,
    task: models.ResearchTask,
    discovery: SourceDiscovery,
    fetched_sources: list[FetchedSource],
    settings: Settings,
    write_event: EventWriter,
) -> list[ParsedSource]:
    storage = build_artifact_storage(settings)
    parsed_sources: list[ParsedSource] = []
    for item in fetched_sources:
        parsed = parse_html(item.fetched.html, prefer_trafilatura=settings.parser_prefer_trafilatura)
        if not is_quality_page(parsed.text, min_chars=settings.min_source_text_chars):
            discovery.summary.low_quality_sources += 1
            discovery.summary.skipped_urls.append(item.canonical_url)
            write_event(
                "source.parse_skipped",
                "parse_source",
                "来源正文质量不足，已跳过。",
                {"url": item.canonical_url, "text_chars": len(parsed.text), "min_chars": settings.min_source_text_chars},
            )
            continue

        content_hash = sha256_text(item.fetched.html)
        social_context = build_social_context(item.result, item.fetched.html, parsed)
        source = models.Source(
            task_id=task.id,
            url=item.fetched.url,
            canonical_url=item.fetched.final_url,
            source_type=item.result.source_type,
            title=(parsed.title or item.result.title)[:255],
            publisher=publisher_from_url(item.fetched.final_url),
            published_at=parse_iso_datetime(social_context.get("published_at")),
            content_hash=content_hash,
            is_primary=item.result.source_type in {"official", "docs"},
            social_platform=social_context.get("platform"),
            sentiment=social_context.get("sentiment"),
            heat_score=social_context.get("heat"),
            interaction_metrics_json=encode_json(social_context.get("interaction_metrics") or {}),
        )
        db.add(source)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            discovery.summary.skipped_urls.append(item.canonical_url)
            continue

        object_key = f"snapshots/{task.id}/{source.id}.html"
        storage.put_bytes(object_key, item.fetched.html.encode("utf-8"), content_type="text/html; charset=utf-8")
        db.add(
            models.SourceArtifact(
                source_id=source.id,
                artifact_type="html_snapshot",
                object_key=object_key,
                sha256=content_hash,
                content_type="text/html; charset=utf-8",
                size_bytes=len(item.fetched.html.encode("utf-8")),
            )
        )
        db.commit()
        parsed_sources.append(ParsedSource(result=item.result, fetched=item.fetched, parsed=parsed, source_id=source.id))

    if fetched_sources and not parsed_sources and discovery.summary.low_quality_sources:
        write_event(
            "source.parse_exhausted",
            "parse_source",
            "All fetched pages were too low quality to parse; downstream workflow will use its fallback path.",
            {
                "fetched_count": len(fetched_sources),
                "low_quality_count": discovery.summary.low_quality_sources,
            },
        )
    return parsed_sources


def extract_research_evidence(
    db: Session,
    *,
    task: models.ResearchTask,
    discovery: SourceDiscovery,
    parsed_sources: list[ParsedSource],
    settings: Settings | None = None,
    write_event: EventWriter,
) -> CollectionSummary:
    keywords = build_keywords(task.prompt, discovery.scope)
    indexer = ElasticsearchIndexer(settings or get_settings())
    for parsed_source in parsed_sources:
        source = db.get(models.Source, parsed_source.source_id)
        if source is None:
            continue

        extracted_items = extract_evidence(parsed_source.parsed.paragraphs, keywords=keywords, max_items=3)
        for item in extracted_items:
            evidence_hash = sha256_text(f"{source.id}:{item.quote}")
            locator = {
                "kind": "html_text",
                "parser": parsed_source.parsed.parser_name,
                "char_start": item.char_start,
                "char_end": item.char_end,
                "url": parsed_source.fetched.final_url,
            }
            social_context = source_social_context(source)
            if social_context:
                locator["social"] = social_context
            db.add(
                models.Evidence(
                    source_id=source.id,
                    quote=item.quote,
                    locator_json=encode_json(locator),
                    evidence_hash=evidence_hash,
                    extraction_method=parsed_source.parsed.parser_name,
                    source_version=1,
                    language=item.language,
                    quality_score=max(item.quality_score, min(parsed_source.result.score, 0.95)),
                )
            )
            discovery.summary.evidence_created += 1

        db.commit()
        discovery.summary.sources_created += 1
        indexer.sync_source_bundle(db, source)
        write_event(
            "source.fetched",
            "fetch_source",
            "来源抓取、解析和快照保存完成。",
            {
                "source_id": source.id,
                "url": parsed_source.fetched.final_url,
                "evidence_count": len(extracted_items),
                "content_type": parsed_source.fetched.content_type,
                "status_code": parsed_source.fetched.status_code,
            },
        )

    if discovery.summary.evidence_created:
        write_event(
            "evidence.created",
            "extract_evidence",
            f"已从真实网页抽取 {discovery.summary.evidence_created} 条 Evidence。",
            {"sources_created": discovery.summary.sources_created, "evidence_created": discovery.summary.evidence_created},
        )
    return discovery.summary


def build_query(prompt: str, scope: dict[str, Any]) -> str:
    competitors = " ".join(scope.get("competitors") or [])
    dimensions = " ".join(scope.get("dimensions") or [])
    return " ".join(part for part in [prompt, competitors, dimensions] if part).strip()


def create_collection_report(db: Session, task: models.ResearchTask, summary: CollectionSummary) -> None:
    existing = db.execute(select(models.Report.id).where(models.Report.task_id == task.id)).first()
    if existing:
        return
    report = models.Report(
        task_id=task.id,
        version=1,
        status="draft",
        citation_coverage=1.0 if summary.evidence_created else 0.0,
        input_snapshot_json=task.scope_json,
        generated_at=models.utc_now(),
    )
    db.add(report)
    db.flush()
    db.add(
        models.ReportSection(
            report_id=report.id,
            section_type="collection_summary",
            title="真实采集摘要",
            content_markdown=(
                f"本轮通过 {summary.provider} 发现 {summary.source_candidates} 个候选来源，"
                f"成功入库 {summary.sources_created} 个 Source，抽取 {summary.evidence_created} 条 Evidence。"
                f"跳过低质量来源 {summary.low_quality_sources} 个，robots 阻止 {summary.robots_blocked} 个。"
            ),
            order_no=1,
        )
    )
    db.commit()


def decode_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    return json.loads(value)


def encode_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_quality_page(text: str, *, min_chars: int) -> bool:
    clean_text = " ".join(text.split())
    if len(clean_text) < min_chars:
        return False
    unique_words = set(clean_text.lower().split())
    if len(unique_words) < 20 and len(clean_text) < 1000:
        return False
    return True


def publisher_from_url(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host.removeprefix("www.")[:120] or "unknown"


def build_social_context(result: SearchResult, html: str, parsed: ParsedPage) -> dict[str, Any]:
    metadata = result.metadata if isinstance(result.metadata, dict) else {}
    social_fields = metadata.get("social_fields") if isinstance(metadata.get("social_fields"), dict) else {}
    if result.source_type != "social" and not social_fields:
        return {}
    context = {
        "platform": metadata.get("platform") or detect_social_platform(result.url),
        "sentiment": social_fields.get("sentiment") or detect_social_sentiment(parsed.text),
        "heat": social_fields.get("heat"),
        "published_at": social_fields.get("published_at") or extract_social_published_at(html),
        "interaction_metrics": dict(social_fields.get("interaction_metrics") or {}),
    }
    interaction_metrics = extract_social_interaction_metrics(html, parsed.text)
    if interaction_metrics:
        context["interaction_metrics"] = interaction_metrics
        if context["heat"] is None:
            context["heat"] = derive_social_heat(interaction_metrics)
    return context


def source_social_context(source: models.Source) -> dict[str, Any]:
    if not source.social_platform:
        return {}
    return {
        "platform": source.social_platform,
        "sentiment": source.sentiment or "unknown",
        "heat": source.heat_score,
        "published_at": source.published_at.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z") if source.published_at else None,
        "interaction_metrics": decode_json(source.interaction_metrics_json),
    }


def detect_social_platform(url: str) -> str:
    return build_public_social_metadata(url).get("platform", "public_social")


def extract_social_published_at(html: str) -> str | None:
    match = re.search(
        r'(?:property|name)=["\'](?:article:published_time|pubdate|publish_date|datePublished)["\'][^>]*content=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(r'<time[^>]*datetime=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    if not match:
        return None
    return normalize_iso_datetime(match.group(1))


def extract_social_interaction_metrics(html: str, text: str) -> dict[str, int]:
    source = f"{html}\n{text}"
    metrics: dict[str, int] = {}
    comment_count = extract_count(source, [r"(\d[\d,\.]*[kKmM]?)\s+comments?", r"comments?\s+(\d[\d,\.]*[kKmM]?)"])
    if comment_count is not None:
        metrics["comment_count"] = comment_count
    like_count = extract_count(source, [r"(\d[\d,\.]*[kKmM]?)\s+upvotes?", r"(\d[\d,\.]*[kKmM]?)\s+likes?", r"likes?\s+(\d[\d,\.]*[kKmM]?)"])
    if like_count is not None:
        metrics["upvote_count"] = like_count
    share_count = extract_count(source, [r"(\d[\d,\.]*[kKmM]?)\s+shares?", r"shares?\s+(\d[\d,\.]*[kKmM]?)"])
    if share_count is not None:
        metrics["share_count"] = share_count
    view_count = extract_count(source, [r"(\d[\d,\.]*[kKmM]?)\s+views?", r"views?\s+(\d[\d,\.]*[kKmM]?)"])
    if view_count is not None:
        metrics["view_count"] = view_count
    return metrics


def detect_social_sentiment(text: str) -> str:
    lowered = text.lower()
    positive_terms = ["great", "good", "love", "helpful", "fast", "smooth", "recommend", "stable", "nice", "liked", "喜欢", "好用", "稳定"]
    negative_terms = ["bad", "slow", "bug", "broken", "expensive", "problem", "hate", "poor", "terrible", "贵", "卡", "崩", "差"]
    positive = sum(1 for term in positive_terms if term in lowered)
    negative = sum(1 for term in negative_terms if term in lowered)
    if positive == negative == 0:
        return "unknown"
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def derive_social_heat(interaction_metrics: dict[str, int]) -> float | None:
    total = sum(max(value, 0) for value in interaction_metrics.values())
    if total <= 0:
        return None
    return round(min(1.0, total / 500.0), 3)


def extract_count(text: str, patterns: list[str]) -> int | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        return normalize_count(match.group(1))
    return None


def normalize_count(value: str) -> int | None:
    cleaned = value.strip().lower().replace(",", "")
    multiplier = 1
    if cleaned.endswith("k"):
        multiplier = 1_000
        cleaned = cleaned[:-1]
    elif cleaned.endswith("m"):
        multiplier = 1_000_000
        cleaned = cleaned[:-1]
    try:
        return int(float(cleaned) * multiplier)
    except ValueError:
        return None


def normalize_iso_datetime(value: str) -> str | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.isoformat()
    return parsed.astimezone(UTC).replace(tzinfo=None).isoformat()


def parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = normalize_iso_datetime(value)
    if not normalized:
        return None
    return datetime.fromisoformat(normalized)
