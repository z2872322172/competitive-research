"""后端单元测试（清单 700）：服务层直接调用——fetcher/robots/parser/LLM 输出校验/claim 抽取/规则降级/重试策略/ArtifactStorage/环境配置/社交采集适配。从 test_api_contract.py 按模块拆出。"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app import models
from app.config import Settings, get_settings
from app.db import SessionLocal, init_db
from app.main import app
from app.services import collection, research_service
from app.services.analysis import claim_extractor, llm
from app.services.claim_quality import analyze_claim_conflict
from app.services.fetching import fetcher as fetcher_module
from app.services.fetching.fetcher import FetchResult
from app.services.fetching.robots import RobotsDecision
from app.services.parsing import html_parser
from app.services.search.adapters import build_search_adapter, classify_source_type
from app.services.search.base import SearchResult
from app.services.social.adapters import PublicSocialUrlAdapter
from app.services.source_quality import score_source_reliability
from app.services.storage import artifacts as artifact_storage
from app.services.storage.artifacts import LocalArtifactStorage


@pytest.fixture(autouse=True)
def disable_real_search(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "")
    get_settings.cache_clear()
    init_db()
    yield
    get_settings.cache_clear()


def test_stage_six_local_artifact_storage_reads_and_writes_text(tmp_path):
    storage = LocalArtifactStorage(tmp_path)

    artifact = storage.put_text("snapshots/task_1/source_1.html", "<html><p>Hello</p></html>")

    assert artifact.object_key == "snapshots/task_1/source_1.html"
    assert storage.read_text("snapshots/task_1/source_1.html") == "<html><p>Hello</p></html>"


def test_source_reliability_scores_official_sources_above_social_signals():
    official = models.Source(
        task_id=1,
        url="https://cursor.com/pricing",
        canonical_url="https://cursor.com/pricing",
        source_type="official",
        title="Cursor Pricing",
        publisher="Cursor",
        content_hash="abc",
        index_status="indexed",
        is_primary=True,
    )
    social = models.Source(
        task_id=1,
        url="http://reddit.com/r/cursor/comments/1",
        canonical_url="http://reddit.com/r/cursor/comments/1",
        source_type="social",
        title="Cursor discussion",
        publisher="Reddit",
        content_hash="",
        index_status="pending",
        is_primary=False,
        heat_score=0.9,
    )

    official_score = score_source_reliability(official)
    social_score = score_source_reliability(social)

    assert official_score["label"] == "high"
    assert official_score["score"] > social_score["score"]
    assert any("一手来源" in reason for reason in official_score["reasons"])
    assert any("社区/社交来源" in warning for warning in social_score["warnings"])


def test_claim_conflict_analysis_prefers_stronger_source_side():
    official = models.Source(
        task_id=1,
        url="https://cursor.com/pricing",
        canonical_url="https://cursor.com/pricing",
        source_type="official",
        title="Cursor Pricing",
        publisher="Cursor",
        content_hash="abc",
        index_status="indexed",
        is_primary=True,
    )
    social = models.Source(
        task_id=1,
        url="http://example.com/discussion",
        canonical_url="http://example.com/discussion",
        source_type="social",
        title="Discussion",
        publisher="Forum",
        content_hash="",
        index_status="pending",
        is_primary=False,
    )
    support = models.Evidence(source_id=1, quote="Official pricing", evidence_hash="s", quality_score=0.9, source=official)
    conflict = models.Evidence(source_id=2, quote="Old community price", evidence_hash="c", quality_score=0.45, source=social)
    claim = models.Claim(
        task_id=1,
        subject="Cursor",
        predicate="has_pricing_signal",
        value_json="{}",
        claim_type="pricing",
        dimension="定价策略",
        status=models.ClaimStatus.conflict.value,
        confidence="medium",
        confidence_score=0.62,
        display_text="Cursor pricing claim has mixed evidence.",
    )
    claim.evidence_links = [
        models.ClaimEvidence(evidence_id=1, relation="supports", weight=1.0, evidence=support),
        models.ClaimEvidence(evidence_id=2, relation="conflicts", weight=1.0, evidence=conflict),
    ]

    analysis = analyze_claim_conflict(claim)

    assert analysis["support_count"] == 1
    assert analysis["conflict_count"] == 1
    assert analysis["preferred_relation"] == "supports"
    assert analysis["needs_more_research"] is True
    assert "披露冲突来源" in analysis["recommendation"]


def test_stage_six_artifact_storage_factory_switches_to_minio(monkeypatch):
    monkeypatch.setattr(artifact_storage.MinioArtifactStorage, "_ensure_bucket_exists", lambda self: None)

    storage = artifact_storage.build_artifact_storage(
        Settings(
            artifact_storage_backend="minio",
            minio_endpoint="http://minio.example:9000",
            minio_access_key="minio",
            minio_secret_key="secret",
            minio_bucket="verda-artifacts",
        )
    )

    assert isinstance(storage, artifact_storage.FallbackArtifactStorage)
    assert isinstance(storage.primary, artifact_storage.MinioArtifactStorage)
    assert storage.primary.bucket == "verda-artifacts"
    assert isinstance(storage.fallback, artifact_storage.LocalArtifactStorage)

def test_stage_six_environment_profiles_apply_runtime_defaults(monkeypatch):
    for key in [
        "APP_ENV",
        "ENVIRONMENT",
        "DATABASE_URL",
        "TASK_MODE",
        "REDIS_URL",
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
    ]:
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    test_settings = get_settings()
    assert test_settings.environment == "test"
    assert test_settings.database_url == "sqlite:///./verda_test.db"
    assert test_settings.task_mode == "inline"
    assert test_settings.redis_url == "redis://localhost:6379/2"
    assert test_settings.celery_result_backend == "redis://localhost:6379/3"

    monkeypatch.setenv("APP_ENV", "prod")
    get_settings.cache_clear()
    prod_settings = get_settings()
    assert prod_settings.environment == "prod"
    assert prod_settings.database_url == "mysql+pymysql://verda:verda@mysql:3306/verda?charset=utf8mb4"
    assert prod_settings.task_mode == "celery"
    assert prod_settings.redis_url == "redis://redis:6379/0"
    assert prod_settings.celery_result_backend == "redis://redis:6379/1"

    get_settings.cache_clear()

def test_stage_six_environment_variables_override_profile_defaults(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./override.db")
    monkeypatch.setenv("TASK_MODE", "inline")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6380/8")
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.environment == "prod"
        assert settings.database_url == "sqlite:///./override.db"
        assert settings.task_mode == "inline"
        assert settings.celery_broker_url == "redis://localhost:6380/8"
        assert settings.celery_result_backend == "redis://redis:6379/1"
    finally:
        get_settings.cache_clear()

def test_stage_six_middleware_ip_overrides_are_composed_from_env(monkeypatch):
    for key in [
        "APP_ENV",
        "DATABASE_URL",
        "MYSQL_HOST",
        "MYSQL_PORT",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "MYSQL_DATABASE",
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_DB",
        "CELERY_RESULT_DB",
        "REDIS_URL",
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
        "ELASTICSEARCH_URL",
        "MINIO_ENDPOINT",
        "MINIO_ACCESS_KEY",
        "MINIO_SECRET_KEY",
        "MINIO_BUCKET",
    ]:
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("MYSQL_HOST", "10.10.0.12")
    monkeypatch.setenv("MYSQL_PORT", "3307")
    monkeypatch.setenv("MYSQL_USER", "research")
    monkeypatch.setenv("MYSQL_PASSWORD", "secret")
    monkeypatch.setenv("MYSQL_DATABASE", "verda_prod")
    monkeypatch.setenv("REDIS_HOST", "10.10.0.13")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("REDIS_DB", "4")
    monkeypatch.setenv("CELERY_RESULT_DB", "5")
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://10.10.0.14:9200")
    monkeypatch.setenv("MINIO_ENDPOINT", "http://10.10.0.15:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "minio-user")
    monkeypatch.setenv("MINIO_SECRET_KEY", "minio-pass")
    monkeypatch.setenv("MINIO_BUCKET", "verda-artifacts")
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.database_url == "mysql+pymysql://research:secret@10.10.0.12:3307/verda_prod?charset=utf8mb4"
        assert settings.redis_url == "redis://10.10.0.13:6380/4"
        assert settings.celery_broker_url == "redis://10.10.0.13:6380/4"
        assert settings.celery_result_backend == "redis://10.10.0.13:6380/5"
        assert settings.elasticsearch_url == "http://10.10.0.14:9200"
        assert settings.minio_endpoint == "http://10.10.0.15:9000"
        assert settings.minio_access_key == "minio-user"
        assert settings.minio_secret_key == "minio-pass"
        assert settings.minio_bucket == "verda-artifacts"
    finally:
        get_settings.cache_clear()

def test_stage_two_service_rules_and_unique_constraints():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        created = client.post(
            "/v1/research-tasks",
            json={
                "prompt": "调研 Trae、Cursor、GitHub Copilot、Windsurf 的竞争格局",
                "competitors": ["Trae", "Cursor"],
                "dimensions": ["产品定位", "定价策略"],
            },
        ).json()
        client.post(f"/v1/research-tasks/{created['id']}/confirm")
        detail = client.get(f"/v1/research-tasks/{created['id']}").json()
        linked_claim = next(item for item in detail["claims"] if item["evidence_links"])
        assert linked_claim["evidence_links"][0]["evidence_id"] in linked_claim["evidence_ids"]
        assert linked_claim["evidence_links"][0]["relation"] in {"supports", "context", "conflicts"}

    db = SessionLocal()
    try:
        task = db.get(models.ResearchTask, created["id"])
        assert task is not None
        with pytest.raises(ValueError, match="invalid_task_transition"):
            research_service.transition_task(task, models.TaskStatus.draft)
        db.rollback()

        existing_link = db.query(models.ClaimEvidence).first()
        assert existing_link is not None
        db.add(
            models.ClaimEvidence(
                claim_id=existing_link.claim_id,
                evidence_id=existing_link.evidence_id,
                relation=existing_link.relation,
                weight=existing_link.weight,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()

def test_stage_three_collects_real_source_and_evidence_without_network(monkeypatch, tmp_path):
    class FakeSearchAdapter:
        def search(self, query: str, *, max_results: int) -> list[SearchResult]:
            assert "Cursor" in query
            return [
                SearchResult(
                    title="Cursor Pricing",
                    url="https://cursor.example/pricing#plans",
                    snippet="Pricing and team controls",
                    score=0.9,
                    source_type="official",
                )
            ]

    class FakeFetcher:
        def __init__(self, **kwargs) -> None:
            pass

        def fetch(self, url: str) -> FetchResult:
            assert url == "https://cursor.example/pricing"
            return FetchResult(
                url=url,
                final_url=url,
                content_type="text/html; charset=utf-8",
                status_code=200,
                html="""
                <html>
                  <head><title>Cursor Pricing</title></head>
                  <body>
                    <h1>Cursor for teams</h1>
                    <p>Cursor Business includes privacy mode, admin controls, centralized billing, and team management for organizations comparing AI coding assistants.</p>
                    <p>Teams can evaluate Cursor against GitHub Copilot and Windsurf by reviewing pricing, collaboration controls, and enterprise readiness.</p>
                  </body>
                </html>
                """,
            )

    monkeypatch.setattr(collection, "build_search_adapter", lambda settings, manual_urls: FakeSearchAdapter())
    monkeypatch.setattr(collection, "HttpPageFetcher", FakeFetcher)

    db = SessionLocal()
    try:
        client_payload = {
            "prompt": "调研 Cursor 的定价策略和企业能力",
            "competitors": ["Cursor"],
            "dimensions": ["定价策略", "企业能力"],
        }
        task = research_service.create_task(db, research_service.ResearchTaskCreate(**client_payload))
        run = research_service.create_run(db, task.id)
        events = []

        summary = collection.collect_research_evidence(
            db,
            task=task,
            run=run,
            settings=Settings(search_provider="test", artifact_storage_dir=str(tmp_path), search_max_results=2, min_source_text_chars=120),
            write_event=lambda event_type, stage, message, payload=None: events.append(event_type),
        )

        assert summary.sources_created == 1
        assert summary.evidence_created >= 1
        assert "evidence.created" in events

        source = db.query(models.Source).filter_by(task_id=task.id).one()
        assert source.canonical_url == "https://cursor.example/pricing"
        assert source.is_primary is True
        assert db.query(models.SourceArtifact).filter_by(source_id=source.id).count() == 1
        assert db.query(models.Evidence).filter_by(source_id=source.id).count() >= 1
    finally:
        db.rollback()
        db.close()

def test_stage_four_rule_based_claim_extraction_binds_evidence(monkeypatch, tmp_path):
    class FakeSearchAdapter:
        def search(self, query: str, *, max_results: int) -> list[SearchResult]:
            return [SearchResult(title="Cursor Pricing", url="https://cursor.example/pricing", score=0.85, source_type="official")]

    class FakeFetcher:
        def __init__(self, **kwargs) -> None:
            pass

        def fetch(self, url: str) -> FetchResult:
            return FetchResult(
                url=url,
                final_url=url,
                content_type="text/html",
                status_code=200,
                html="""
                <html>
                  <head><title>Cursor Pricing</title></head>
                  <body>
                    <p>Cursor pricing includes team billing, admin controls, privacy settings, and enterprise workflow support for AI coding teams.</p>
                    <p>Cursor Business gives organizations a way to manage seats and evaluate AI coding assistant governance needs.</p>
                  </body>
                </html>
                """,
            )

    monkeypatch.setattr(collection, "build_search_adapter", lambda settings, manual_urls: FakeSearchAdapter())
    monkeypatch.setattr(collection, "HttpPageFetcher", FakeFetcher)

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor pricing and enterprise workflow support",
                competitors=["Cursor"],
                dimensions=["pricing", "enterprise features"],
            ),
        )
        run = research_service.create_run(db, task.id)
        collection.collect_research_evidence(
            db,
            task=task,
            run=run,
            settings=Settings(search_provider="test", artifact_storage_dir=str(tmp_path), min_source_text_chars=120),
            write_event=lambda event_type, stage, message, payload=None: None,
        )

        result = claim_extractor.extract_and_store_claims(
            db,
            task=task,
            settings=Settings(search_provider="test", artifact_storage_dir=str(tmp_path), llm_max_evidence_items=4),
        )

        assert len(result.claims) >= 1
        stored_claim = db.query(models.Claim).filter_by(task_id=task.id).one()
        assert stored_claim.evidence_coverage == 1.0
        assert stored_claim.claim_type in {"pricing", "feature"}
        assert db.query(models.ClaimEvidence).filter_by(claim_id=stored_claim.id).count() == 1
    finally:
        db.rollback()
        db.close()

def test_stage_four_repairs_messy_llm_claim_output():
    content = """
    Here is the JSON:
    ```json
    [
      {
        "evidence_id": "ev_123",
        "subject": "Cursor",
        "predicate": "Has Pricing Signal",
        "value": {"summary": "Cursor pricing includes team billing."},
        "claim_type": "pricing_signal",
        "dimension": "定价策略",
        "status": "certain",
        "confidence": "very_high",
        "confidence_score": "0.82",
        "display_text": "Cursor pricing includes team billing for organizations.",
        "relation": "supporting"
      }
    ]
    ```
    """

    result = llm.parse_claim_extraction_content(content)

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.claim_type == "pricing"
    assert claim.status == "verified"
    assert claim.confidence == "high"
    assert claim.confidence_score == 0.82
    assert claim.predicate == "has_pricing_signal"
    assert claim.relation == "supports"

def test_stage_four_llm_schema_failure_is_not_silently_fallback(monkeypatch):
    class BrokenLLMExtractor:
        def extract_claims(self, *, prompt: str, evidence_payload: list[dict]):
            raise ValueError("invalid_claim_json:Expecting value")

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor LLM schema failure propagation",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        research_service.seed_demo_research_objects(db, task.id)
        monkeypatch.setattr(claim_extractor, "build_llm_extractor", lambda settings: BrokenLLMExtractor())

        with pytest.raises(ValueError, match="schema_validation_failed:invalid_claim_json"):
            claim_extractor.extract_and_store_claims(
                db,
                task=task,
                settings=Settings(search_provider="test", llm_api_key="test-key"),
            )
    finally:
        db.rollback()
        db.close()

def test_stage_four_report_generation_retries_and_records_failure_event(monkeypatch):
    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="调研 Cursor 的定价和企业功能",
                competitors=["Cursor"],
                dimensions=["定价策略", "企业能力"],
            ),
        )
        run = research_service.create_run(db, task.id)
        research_service.seed_demo_research_objects(db, task.id)
        db.query(models.ReportSection).delete()
        db.query(models.Report).delete()
        db.commit()

        calls = {"count": 0}
        original_create_claim_report = research_service.create_claim_report

        def flaky_create_claim_report(db, task, summary, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("temporary report renderer failure")
            return original_create_claim_report(db, task, summary, **kwargs)

        monkeypatch.setattr(research_service, "extract_research_evidence", lambda *args, **kwargs: collection.CollectionSummary(provider="test", evidence_created=1, sources_created=1))
        monkeypatch.setattr(research_service, "extract_and_store_claims", lambda *args, **kwargs: claim_extractor.ClaimExtractionResult(claims=[]))
        monkeypatch.setattr(research_service, "create_claim_report", flaky_create_claim_report)

        result = research_service.simulate_research_run(db, run.id)

        assert result.status == models.RunStatus.waiting_review.value
        assert calls["count"] == 2
        failure_event = db.query(models.ResearchEvent).filter_by(run_id=run.id, type="report.generate_failed").one()
        assert "temporary report renderer failure" in failure_event.message
        assert db.query(models.Report).filter_by(task_id=task.id).count() == 1
    finally:
        db.rollback()
        db.close()

def test_stage_three_discoveries_emit_search_exhausted_when_adapter_returns_no_results(monkeypatch):
    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor pricing and enterprise controls",
                competitors=["Cursor"],
                dimensions=["pricing", "enterprise controls"],
            ),
        )

        class FakeSearchAdapter:
            def search(self, query: str, *, max_results: int) -> list[SearchResult]:
                assert "Cursor" in query
                return []

        events: list[tuple[str, str, str, dict | None]] = []
        monkeypatch.setattr(collection, "build_search_adapter", lambda settings, manual_urls: FakeSearchAdapter())

        discovery = collection.discover_research_sources(
            db,
            task=task,
            settings=Settings(search_provider="test"),
            write_event=lambda event_type, stage, message, payload=None: events.append((event_type, stage, message, payload)),
        )

        assert discovery.summary.searched is True
        assert discovery.summary.source_candidates == 0
        assert [event_type for event_type, *_ in events if event_type == "source.search_exhausted"] == ["source.search_exhausted"]
        assert not any(event_type == "node.failed" for event_type, *_ in events)
    finally:
        db.rollback()
        db.close()

def test_stage_three_skips_low_quality_pages_without_network(monkeypatch, tmp_path):
    class FakeSearchAdapter:
        def search(self, query: str, *, max_results: int) -> list[SearchResult]:
            return [SearchResult(title="Thin page", url="https://thin.example/page", source_type="web")]

    class FakeFetcher:
        def __init__(self, **kwargs) -> None:
            pass

        def fetch(self, url: str) -> FetchResult:
            return FetchResult(
                url=url,
                final_url=url,
                content_type="text/html",
                status_code=200,
                html="<html><head><title>Thin</title></head><body><p>Too short to become evidence.</p></body></html>",
            )

    monkeypatch.setattr(collection, "build_search_adapter", lambda settings, manual_urls: FakeSearchAdapter())
    monkeypatch.setattr(collection, "HttpPageFetcher", FakeFetcher)

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor AI code editor pricing and enterprise features",
                competitors=["Cursor"],
                dimensions=["pricing"],
            ),
        )
        run = research_service.create_run(db, task.id)
        events = []
        summary = collection.collect_research_evidence(
            db,
            task=task,
            run=run,
            settings=Settings(search_provider="test", artifact_storage_dir=str(tmp_path), min_source_text_chars=120),
            write_event=lambda event_type, stage, message, payload=None: events.append(event_type),
        )
        assert summary.low_quality_sources == 1
        assert summary.sources_created == 0
        assert "source.parse_skipped" in events
    finally:
        db.rollback()
        db.close()

def test_stage_three_classifies_public_social_urls_as_social():
    assert classify_source_type("https://www.reddit.com/r/Cursor/comments/abc123/cursor_pricing_discussion/") == "social"
    assert classify_source_type("https://x.com/cursor_ai/status/1234567890") == "social"

def test_stage_three_manual_urls_work_without_tavily_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    get_settings.cache_clear()

    db = SessionLocal()
    try:
        manual_adapter = build_search_adapter(
            Settings(search_provider="tavily", tavily_api_key="", artifact_storage_dir=str(tmp_path)),
            manual_urls=["https://manual.example/source"],
        )
        assert manual_adapter.search("Cursor manual URL flow", max_results=1)[0].url == "https://manual.example/source"

        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor manual URL flow",
                competitors=["Cursor"],
                dimensions=["workflow"],
                source_preferences=["https://manual.example/source"],
            ),
        )

        discovery = collection.discover_research_sources(
            db,
            task=task,
            settings=Settings(search_provider="tavily", tavily_api_key="", artifact_storage_dir=str(tmp_path)),
            write_event=lambda *args, **kwargs: None,
        )

        assert discovery.summary.searched is True
        assert discovery.results[0].url == "https://manual.example/source"
        assert discovery.results[0].source_type == "web"
    finally:
        db.rollback()
        db.close()
        get_settings.cache_clear()

def test_stage_four_build_llm_extractor_is_optional_without_api_key():
    assert llm.build_llm_extractor(Settings(search_provider="test", llm_api_key="")) is None

def test_stage_four_build_llm_extractor_enables_openai_compatible_with_api_key():
    extractor = llm.build_llm_extractor(
        Settings(
            search_provider="test",
            llm_api_key="test-key",
            llm_provider="openai_compatible",
            _env_file=None,
        )
    )

    assert extractor is not None
    assert extractor.api_key == "test-key"
    assert extractor.base_url == "https://api.openai.com/v1"

def test_stage_three_discovers_social_candidates_from_source_preferences(monkeypatch, tmp_path):
    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor social discussion signals",
                competitors=["Cursor"],
                dimensions=["market sentiment"],
                source_preferences=[
                    "https://www.reddit.com/r/Cursor/comments/abc123/cursor_pricing_discussion/",
                ],
            ),
        )

        events = []
        discovery = collection.discover_research_sources(
            db,
            task=task,
            settings=Settings(search_provider="test", artifact_storage_dir=str(tmp_path)),
            write_event=lambda event_type, stage, message, payload=None: events.append((event_type, stage, message, payload)),
        )

        assert discovery.summary.searched is True
        assert discovery.summary.source_candidates == 1
        assert discovery.results[0].url == "https://www.reddit.com/r/Cursor/comments/abc123/cursor_pricing_discussion/"
        assert discovery.results[0].source_type == "social"
        assert any(event_type == "source.found" for event_type, *_ in events)
    finally:
        db.rollback()
        db.close()

def test_stage_three_public_social_adapter_attaches_platform_metadata():
    adapter = PublicSocialUrlAdapter(
        ["https://www.reddit.com/r/Cursor/comments/abc123/cursor_pricing_discussion/"]
    )

    result = adapter.search("Cursor pricing", max_results=1)[0]

    assert result.source_type == "social"
    assert result.metadata["platform"] == "reddit"
    assert result.metadata["social_fields"]["sentiment"] == "unknown"
    assert result.metadata["social_fields"]["heat"] is None
    assert result.metadata["social_fields"]["published_at"] is None
    assert result.metadata["social_fields"]["interaction_metrics"] == {}

def test_stage_three_social_pages_surface_public_metadata(monkeypatch, tmp_path):
    class FakeSearchAdapter:
        def search(self, query: str, *, max_results: int) -> list[SearchResult]:
            return [
                SearchResult(
                    title="Cursor subreddit discussion",
                    url="https://www.reddit.com/r/Cursor/comments/abc123/cursor_pricing_discussion/",
                    source_type="social",
                    metadata={
                        "platform": "reddit",
                        "social_fields": {
                            "sentiment": "unknown",
                            "heat": None,
                            "published_at": None,
                            "interaction_metrics": {},
                        },
                    },
                )
            ]

    class FakeFetcher:
        def __init__(self, **kwargs) -> None:
            pass

        def fetch(self, url: str) -> FetchResult:
            return FetchResult(
                url=url,
                final_url=url,
                content_type="text/html",
                status_code=200,
                html=(
                    "<html><head>"
                    '<meta property="article:published_time" content="2026-08-01T12:34:56Z">'
                    "<title>Cursor pricing discussion</title>"
                    "</head><body>"
                    "<article>"
                    "<p>People are comparing Cursor pricing, team controls, and community reactions to the latest product changes.</p>"
                    "<p>42 comments 128 upvotes 18 shares, with several users discussing pricing pressure, enterprise needs, and workflow fit.</p>"
                    "</article>"
                    "</body></html>"
                ),
            )

    monkeypatch.setattr(collection, "build_search_adapter", lambda settings, manual_urls: FakeSearchAdapter())
    monkeypatch.setattr(collection, "HttpPageFetcher", FakeFetcher)

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor social discussion signals",
                competitors=["Cursor"],
                dimensions=["market sentiment"],
                source_preferences=[
                    "https://www.reddit.com/r/Cursor/comments/abc123/cursor_pricing_discussion/",
                ],
            ),
        )
        run = research_service.create_run(db, task.id)
        summary = collection.collect_research_evidence(
            db,
            task=task,
            run=run,
            settings=Settings(
                search_provider="test",
                artifact_storage_dir=str(tmp_path),
                min_source_text_chars=80,
                parser_prefer_trafilatura=False,
            ),
            write_event=lambda *args, **kwargs: None,
        )

        assert summary.sources_created == 1
        source = db.query(models.Source).filter_by(task_id=task.id).one()
        assert source.source_type == "social"
        assert source.published_at is not None

        evidence = (
            db.query(models.Evidence)
            .join(models.Source)
            .filter(models.Source.task_id == task.id)
            .order_by(models.Evidence.created_at.asc())
            .first()
        )
        assert evidence is not None
        locator = research_service.decode_json(evidence.locator_json)
        assert locator["social"]["platform"] == "reddit"
        assert locator["social"]["published_at"] == "2026-08-01T12:34:56Z"
        assert locator["social"]["interaction_metrics"]["comment_count"] == 42
        assert locator["social"]["interaction_metrics"]["upvote_count"] == 128
    finally:
        db.rollback()
        db.close()

def test_fetcher_blocks_robots_disallowed_without_network():
    class DenyRobots:
        def can_fetch(self, url: str, user_agent: str) -> RobotsDecision:
            return RobotsDecision(allowed=False, robots_url="https://example.com/robots.txt")

    fetcher = fetcher_module.HttpPageFetcher(timeout_seconds=1, user_agent="TestBot", robots_policy=DenyRobots())

    with pytest.raises(fetcher_module.WebFetchError, match="robots_disallowed"):
        fetcher.fetch("https://example.com/private")

def test_fetcher_retries_transient_errors_without_network(monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        headers = {"content-type": "text/html; charset=utf-8"}
        content = b"<html><body><p>This page has enough readable text for the fetcher retry smoke test.</p></body></html>"
        text = content.decode("utf-8")
        url = "https://example.com/page"
        status_code = 200

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def get(self, url: str):
            calls["count"] += 1
            if calls["count"] == 1:
                raise fetcher_module.httpx.ConnectError("temporary failure")
            return FakeResponse()

    monkeypatch.setattr(fetcher_module.httpx, "Client", FakeClient)
    fetcher = fetcher_module.HttpPageFetcher(
        timeout_seconds=1,
        user_agent="TestBot",
        max_retries=1,
        retry_backoff_seconds=0,
        max_bytes=10_000,
    )

    result = fetcher.fetch("https://example.com/page#section")

    assert calls["count"] == 2
    assert result.final_url == "https://example.com/page"

def test_parser_prefers_trafilatura_when_available(monkeypatch):
    html = """
    <html>
      <head><title>Readable Page</title></head>
      <body>
        <nav>This navigation text should be ignored by trafilatura.</nav>
        <article><p>The real article explains Cursor pricing, enterprise controls, and team governance for AI coding workflows.</p></article>
      </body>
    </html>
    """

    def fake_extract(*args, **kwargs) -> str:
        return "The real article explains Cursor pricing, enterprise controls, and team governance for AI coding workflows."

    monkeypatch.setattr(html_parser, "load_trafilatura_extract", lambda: fake_extract)

    parsed = html_parser.parse_html(html)

    assert parsed.parser_name == "trafilatura"
    assert parsed.paragraphs == ["The real article explains Cursor pricing, enterprise controls, and team governance for AI coding workflows."]

def test_parser_falls_back_when_trafilatura_is_unavailable(monkeypatch):
    html = """
    <html>
      <head><title>Fallback Page</title></head>
      <body><p>This fallback paragraph is long enough to be retained by the basic parser when Trafilatura is unavailable.</p></body>
    </html>
    """

    monkeypatch.setattr(html_parser, "load_trafilatura_extract", lambda: None)

    parsed = html_parser.parse_html(html)

    assert parsed.parser_name == "stdlib_html_parser"
    assert parsed.paragraphs == ["This fallback paragraph is long enough to be retained by the basic parser when Trafilatura is unavailable."]

def test_stage_four_llm_content_without_json_raises_claim_json_not_found():
    with pytest.raises(ValueError, match="claim_json_not_found"):
        llm.parse_claim_extraction_content("Sorry, I cannot answer that question in JSON format.")

def test_stage_four_llm_unterminated_json_raises_claim_json_not_closed():
    # JSON 完全没有闭合括号时，明确报 claim_json_not_closed
    with pytest.raises(ValueError, match="claim_json_not_closed"):
        llm.parse_claim_extraction_content('Here you go: {"claims": [')
    # 截断的 JSON（外层 } 缺失但内部有 }）会先被截取，再以 invalid_claim_json 报出
    with pytest.raises(ValueError, match="invalid_claim_json"):
        llm.parse_claim_extraction_content('Here you go: {"claims": [{"evidence_id": "ev_1"}]')
    # fenced JSON 块跳过闭合检查，直接进入 json.loads
    with pytest.raises(ValueError, match="invalid_claim_json"):
        llm.parse_claim_extraction_content('```json\n{"claims": [\n```')

def test_stage_four_llm_non_object_payload_raises_claim_payload_must_be_object():
    # 顶层是标量（非对象非数组）时拒绝
    with pytest.raises(ValueError, match="claim_payload_must_be_object"):
        llm.parse_claim_extraction_content('```json\n42\n```')
    # 顶层数组会被包成 claims 数组，元素非对象时被过滤为空结果而不是报错
    result = llm.parse_claim_extraction_content('```json\n["just", "a", "list"]\n```')
    assert result.claims == []

def test_stage_four_llm_non_array_claims_raises_claim_payload_claims_must_be_array():
    with pytest.raises(ValueError, match="claim_payload_claims_must_be_array"):
        llm.parse_claim_extraction_content('{"claims": {"evidence_id": "ev_1"}}')

def test_stage_four_llm_claims_with_unknown_evidence_ids_are_filtered(monkeypatch):
    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor LLM unknown evidence id filtering",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        research_service.seed_demo_research_objects(db, task.id)
        valid_evidence_id = db.query(models.Evidence).join(models.Source).filter(models.Source.task_id == task.id).first().id

        class PartiallyBrokenLLMExtractor:
            def extract_claims(self, *, prompt: str, evidence_payload: list[dict]):
                return llm.parse_claim_extraction_content(
                    json.dumps(
                        {
                            "claims": [
                                {
                                    "evidence_id": "ev_does_not_exist",
                                    "subject": "Cursor",
                                    "predicate": "states_fact",
                                    "display_text": "Claim bound to a hallucinated evidence id.",
                                },
                                {
                                    "evidence_id": valid_evidence_id,
                                    "subject": "Cursor",
                                    "predicate": "states_fact",
                                    "display_text": "Claim bound to a real evidence id.",
                                },
                            ]
                        }
                    )
                )

        monkeypatch.setattr(claim_extractor, "build_llm_extractor", lambda settings: PartiallyBrokenLLMExtractor())

        result = claim_extractor.extract_and_store_claims(
            db,
            task=task,
            settings=Settings(search_provider="test", llm_api_key="test-key"),
        )

        stored_ids = {claim.evidence_id for claim in result.claims}
        assert stored_ids == {valid_evidence_id}, "未知 evidence_id 的 Claim 必须被过滤，不允许产生无证据结论"
    finally:
        db.rollback()
        db.close()

def test_stage_four_llm_runtime_failure_falls_back_to_rule_based(monkeypatch):
    class UnreachableLLMExtractor:
        def extract_claims(self, *, prompt: str, evidence_payload: list[dict]):
            raise llm.LLMUnavailable("connection refused by upstream provider")

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor LLM unavailable fallback",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        research_service.seed_demo_research_objects(db, task.id)
        monkeypatch.setattr(claim_extractor, "build_llm_extractor", lambda settings: UnreachableLLMExtractor())

        result = claim_extractor.extract_and_store_claims(
            db,
            task=task,
            settings=Settings(search_provider="test", llm_api_key="test-key"),
        )

        assert result.claims, "LLM 运行时不可用时应回退到规则抽取并继续产出 Claim"
        assert all(claim.evidence_id for claim in result.claims)
    finally:
        db.rollback()
        db.close()

def test_stage_four_report_generation_retry_exhaustion_raises_runtime_error(monkeypatch):
    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="调研 Cursor 报告重试耗尽行为",
                competitors=["Cursor"],
                dimensions=["定价策略"],
            ),
        )
        run = research_service.create_run(db, task.id)
        research_service.seed_demo_research_objects(db, task.id)
        db.query(models.ReportSection).delete()
        db.query(models.Report).delete()
        db.commit()

        calls = {"count": 0}

        def always_failing_create_claim_report(db, task, summary, **kwargs):
            calls["count"] += 1
            raise RuntimeError(f"persistent renderer failure #{calls['count']}")

        monkeypatch.setattr(research_service, "create_claim_report", always_failing_create_claim_report)

        with pytest.raises(RuntimeError, match="report_generation_failed:persistent renderer failure"):
            research_service.generate_report_with_retry(
                db,
                task=task,
                run=run,
                summary=collection.CollectionSummary(provider="test", evidence_created=1, sources_created=1),
            )

        assert calls["count"] == research_service.REPORT_MAX_ATTEMPTS
        failure_events = (
            db.query(models.ResearchEvent)
            .filter_by(run_id=run.id, type="report.generate_failed")
            .order_by(models.ResearchEvent.sequence_no.asc())
            .all()
        )
        assert len(failure_events) == research_service.REPORT_MAX_ATTEMPTS
        assert [event.severity for event in failure_events] == ["warning", "warning", "error"]
        assert db.query(models.Report).filter_by(task_id=task.id).count() == 0
    finally:
        db.rollback()
        db.close()

def test_fetcher_retry_exhaustion_raises_last_http_error(monkeypatch):
    calls = {"count": 0}

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

        def get(self, url: str):
            calls["count"] += 1
            raise fetcher_module.httpx.ConnectError(f"persistent failure #{calls['count']}")

    monkeypatch.setattr(fetcher_module.httpx, "Client", FakeClient)
    fetcher = fetcher_module.HttpPageFetcher(
        timeout_seconds=1,
        user_agent="TestBot",
        max_retries=2,
        retry_backoff_seconds=0,
        max_bytes=10_000,
    )

    with pytest.raises(fetcher_module.httpx.ConnectError, match="persistent failure #3"):
        fetcher.fetch("https://example.com/flaky")

    assert calls["count"] == 3
