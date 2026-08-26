from fastapi.testclient import TestClient
import json
import pytest
from sqlalchemy.exc import IntegrityError

from app import models
from app.config import Settings, get_settings
from app.db import SessionLocal, init_db
from app.main import app
from app.services import collection
from app.services.analysis import claim_extractor, llm
from app.services.fetching import fetcher as fetcher_module
from app.services.fetching.fetcher import FetchResult
from app.services.fetching.robots import RobotsDecision
from app.services.parsing import html_parser
from app.services import research_service
from app.services.search.adapters import build_search_adapter, classify_source_type
from app.services.search.base import SearchResult
from app.services.search import indexing as search_indexing
from app.services.social.adapters import PublicSocialUrlAdapter
from app.services.storage import artifacts as artifact_storage
from app.services.storage.artifacts import LocalArtifactStorage


@pytest.fixture(autouse=True)
def disable_real_search(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "")
    get_settings.cache_clear()
    init_db()
    yield
    get_settings.cache_clear()


def test_demo_research_flow():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        payload = {
            "prompt": "调研 Trae、Cursor、GitHub Copilot、Windsurf 的竞争格局",
            "competitors": ["Trae", "Cursor", "GitHub Copilot", "Windsurf"],
            "dimensions": ["产品定位", "核心功能", "定价策略"],
        }
        created = client.post("/v1/research-tasks", json=payload)
        assert created.status_code == 201
        task_id = created.json()["id"]

        confirmed = client.post(f"/v1/research-tasks/{task_id}/confirm")
        assert confirmed.status_code == 200
        run_body = confirmed.json()
        assert run_body["status"] == "waiting_review"
        assert run_body["current_stage"] == "review_gate"
        assert run_body["input_snapshot"]["competitors"] == payload["competitors"]
        assert run_body["input_snapshot"]["dimensions"] == payload["dimensions"]
        assert run_body["started_at"] is not None
        assert run_body["finished_at"] is not None

        detail = client.get(f"/v1/research-tasks/{task_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert set(body) == {"task", "latest_run", "runs", "sources", "evidence", "claims", "reports"}
        assert body["task"]["status"] == "waiting_review"
        assert body["task"]["current_run_id"] == run_body["id"]
        assert body["latest_run"]["id"] == run_body["id"]
        assert [run["id"] for run in body["runs"]] == [run_body["id"]]
        assert body["runs"][0]["input_snapshot"]["competitors"] == payload["competitors"]
        assert len(body["evidence"]) >= 3
        assert len(body["claims"]) >= 3
        assert len(body["reports"]) == 1

        source = body["sources"][0]
        assert {
            "id",
            "task_id",
            "url",
            "canonical_url",
            "source_type",
            "title",
            "publisher",
            "retrieved_at",
            "content_hash",
            "index_status",
            "is_primary",
        }.issubset(source)
        assert source["task_id"] == task_id
        assert source["canonical_url"].startswith("https://")

        evidence = body["evidence"][0]
        assert {"id", "source_id", "quote", "locator", "evidence_hash", "extraction_method", "quality_score", "source"}.issubset(evidence)
        assert evidence["quote"]
        assert evidence["source"]["id"] == evidence["source_id"]

        claim = body["claims"][0]
        assert {"id", "task_id", "status", "confidence_score", "display_text", "evidence_ids", "include_in_report"}.issubset(claim)
        assert claim["task_id"] == task_id
        assert claim["evidence_ids"]
        assert 0 <= claim["confidence_score"] <= 1

        report = body["reports"][0]
        assert report["version"] == 1
        assert report["status"] == "draft"
        assert report["citation_coverage"] >= 0
        assert [section["section_type"] for section in report["sections"]] == [
            "executive_summary",
            "comparison",
        ]

        events = client.get(f"/v1/research-tasks/{task_id}/events?after=3")
        assert events.status_code == 200
        assert all(event["sequence_no"] > 3 for event in events.json())
        full_events = client.get(f"/v1/research-tasks/{task_id}/events")
        assert full_events.status_code == 200
        event_body = full_events.json()
        assert [event["sequence_no"] for event in event_body] == list(range(1, len(event_body) + 1))
        domain_event_body = [event for event in event_body if not event["type"].startswith("node.")]
        assert [event["type"] for event in domain_event_body] == [
            "planning.started",
            "search.skipped",
            "search.started",
            "source.found",
            "evidence.created",
            "claim.created",
            "review.required",
            "report.created",
        ]
        assert [event["stage"] for event in domain_event_body] == [
            "plan_research",
            "discover_sources",
            "discover_sources",
            "fetch_source",
            "extract_evidence",
            "verify_claims",
            "review_gate",
            "generate_report",
        ]

        report_id = report["id"]
        markdown_export = client.post(f"/v1/reports/{report_id}/export?format=markdown")
        pdf_export = client.post(f"/v1/reports/{report_id}/export?format=pdf")
        docx_export = client.post(f"/v1/reports/{report_id}/export?format=docx")
        unknown_export = client.post(f"/v1/reports/{report_id}/export?format=txt")

        assert markdown_export.status_code == 200
        assert "执行摘要" in markdown_export.json()["content"]
        assert pdf_export.status_code == 200
        assert pdf_export.headers["content-type"].startswith("application/pdf")
        assert len(pdf_export.content) > 100
        assert docx_export.status_code == 200
        assert docx_export.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert len(docx_export.content) > 100
        assert unknown_export.status_code == 400


def test_deep_research_task_runs_without_competitors_or_demo_competitor_claims():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        payload = {
            "prompt": "Research how enterprises should evaluate retrieval augmented generation frameworks for internal knowledge bases",
            "research_type": "deep_research",
            "template": "generic_deep_research",
            "research_question": "How should enterprises evaluate RAG frameworks for internal knowledge bases?",
            "research_aspects": ["architecture fit", "operational risk", "source governance"],
            "source_preferences": [],
        }

        created = client.post("/v1/research-tasks", json=payload)

        assert created.status_code == 201
        task_body = created.json()
        assert task_body["scope"]["research_type"] == "deep_research"
        assert task_body["scope"]["template"] == "generic_deep_research"
        assert task_body["scope"]["research_question"] == payload["research_question"]
        assert task_body["scope"]["research_aspects"] == payload["research_aspects"]
        assert task_body["scope"]["competitors"] == []

        confirmed = client.post(f"/v1/research-tasks/{task_body['id']}/confirm")
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "completed"

        detail = client.get(f"/v1/research-tasks/{task_body['id']}")
        assert detail.status_code == 200
        detail_body = detail.json()
        assert detail_body["task"]["status"] == "completed"
        assert detail_body["latest_run"]["status"] == "completed"
        subjects = {claim["subject"] for claim in detail_body["claims"]}
        assert detail_body["claims"]
        assert not (subjects & {"Trae", "Cursor", "GitHub Copilot", "Windsurf"})
        assert any("RAG" in claim["display_text"] for claim in detail_body["claims"])
        assert detail_body["reports"]


def test_stage_seven_task_detail_filters_evidence_by_source_competitor_and_dimension():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        payload = {
            "prompt": "Research Trae, Cursor, GitHub Copilot, and Windsurf evidence filtering",
            "competitors": ["Trae", "Cursor", "GitHub Copilot", "Windsurf"],
            "dimensions": ["technical capabilities", "pricing strategy"],
        }
        created = client.post("/v1/research-tasks", json=payload)
        assert created.status_code == 201
        task_id = created.json()["id"]
        confirmed = client.post(f"/v1/research-tasks/{task_id}/confirm")
        assert confirmed.status_code == 200

        detail = client.get(f"/v1/research-tasks/{task_id}").json()
        all_evidence_ids = {item["id"] for item in detail["evidence"]}
        assert len(all_evidence_ids) >= 3

        official = client.get(f"/v1/research-tasks/{task_id}?evidence_source_type=official")
        assert official.status_code == 200
        official_evidence = official.json()["evidence"]
        assert official_evidence
        assert {item["id"] for item in official_evidence} < all_evidence_ids
        assert all(item["source"]["source_type"] == "official" for item in official_evidence)

        cursor_claim_evidence_ids = {
            evidence_id
            for claim in detail["claims"]
            if claim["subject"] == "Cursor"
            for evidence_id in claim["evidence_ids"]
        }
        cursor = client.get(f"/v1/research-tasks/{task_id}?evidence_competitor=Cursor")
        assert cursor.status_code == 200
        cursor_evidence = cursor.json()["evidence"]
        assert cursor_evidence
        assert {item["id"] for item in cursor_evidence} == cursor_claim_evidence_ids

        pricing_claim_evidence_ids = {
            evidence_id
            for claim in detail["claims"]
            if claim["claim_type"] == "pricing"
            for evidence_id in claim["evidence_ids"]
        }
        pricing = client.get(f"/v1/research-tasks/{task_id}?evidence_dimension=pricing")
        assert pricing.status_code == 200
        pricing_evidence = pricing.json()["evidence"]
        assert pricing_evidence
        assert {item["id"] for item in pricing_evidence} == pricing_claim_evidence_ids


def test_report_export_persists_artifacts(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTIFACT_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    db = SessionLocal()
    try:
        with TestClient(app) as client:
            client.delete("/v1/dev/demo-data")
            task = client.post(
                "/v1/research-tasks",
                json={
                    "prompt": "Analyze Cursor pricing changes and enterprise controls",
                    "competitors": ["Cursor"],
                    "dimensions": ["pricing"],
                },
            ).json()
            client.post(f"/v1/research-tasks/{task['id']}/confirm")
            report = client.get(f"/v1/research-tasks/{task['id']}").json()["reports"][0]

            markdown_export = client.post(f"/v1/reports/{report['id']}/export?format=markdown")
            pdf_export = client.post(f"/v1/reports/{report['id']}/export?format=pdf")
            docx_export = client.post(f"/v1/reports/{report['id']}/export?format=docx")

            assert markdown_export.status_code == 200
            assert markdown_export.headers["x-artifact-object-key"].startswith(f"reports/{task['id']}/")
            assert pdf_export.status_code == 200
            assert docx_export.status_code == 200

        report_artifacts = (
            db.query(models.ReportArtifact)
            .join(models.Report)
            .filter(models.Report.task_id == task["id"])
            .order_by(models.ReportArtifact.created_at.asc())
            .all()
        )
        assert {artifact.artifact_type for artifact in report_artifacts} == {"markdown", "pdf", "docx"}
        assert all(artifact.object_key.startswith(f"reports/{task['id']}/") for artifact in report_artifacts)
    finally:
        db.close()
        get_settings.cache_clear()


def test_stage_seven_source_snapshot_returns_readable_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTIFACT_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        db = SessionLocal()
        try:
            task = models.ResearchTask(title="Snapshot source", prompt="Research Cursor snapshot support")
            db.add(task)
            db.flush()
            source = models.Source(
                task_id=task.id,
                url="https://cursor.example/pricing",
                canonical_url="https://cursor.example/pricing",
                source_type="official",
                title="Cursor Pricing",
                publisher="Cursor",
                content_hash="abc123",
            )
            db.add(source)
            db.flush()
            object_key = f"snapshots/{task.id}/{source.id}.html"
            snapshot_path = tmp_path / object_key
            snapshot_path.parent.mkdir(parents=True)
            snapshot_path.write_text(
                "<html><body><h1>Cursor Pricing</h1><p>Teams plan includes privacy controls and admin policy support.</p></body></html>",
                encoding="utf-8",
            )
            db.add(
                models.SourceArtifact(
                    source_id=source.id,
                    artifact_type="html_snapshot",
                    object_key=object_key,
                    sha256="abc123",
                )
            )
            db.commit()
            source_id = source.id
        finally:
            db.close()

        response = client.get(f"/v1/sources/{source_id}/snapshot")

        assert response.status_code == 200
        body = response.json()
        assert body["source_id"] == source_id
        assert body["artifact_type"] == "html_snapshot"
        assert body["available"] is True
        assert body["content_hash"] == "abc123"
        assert body["object_key"].endswith(".html")
        assert "Cursor Pricing" in body["summary"]
        assert "privacy controls" in body["summary"]
        assert body["char_count"] > 0

    get_settings.cache_clear()


def test_stage_seven_source_snapshot_reports_unavailable_without_file(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTIFACT_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        db = SessionLocal()
        try:
            task = models.ResearchTask(title="Missing snapshot", prompt="Research missing snapshot support")
            db.add(task)
            db.flush()
            source = models.Source(
                task_id=task.id,
                url="https://example.com/missing",
                canonical_url="https://example.com/missing",
                source_type="docs",
                title="Missing Snapshot",
                publisher="Example",
                content_hash="missing123",
            )
            db.add(source)
            db.flush()
            db.add(
                models.SourceArtifact(
                    source_id=source.id,
                    artifact_type="html_snapshot",
                    object_key=f"snapshots/{task.id}/{source.id}.html",
                    sha256="missing123",
                )
            )
            db.commit()
            source_id = source.id
        finally:
            db.close()

        response = client.get(f"/v1/sources/{source_id}/snapshot")
        missing_source = client.get("/v1/sources/src_unknown/snapshot")

        assert response.status_code == 200
        body = response.json()
        assert body["source_id"] == source_id
        assert body["artifact_type"] == "html_snapshot"
        assert body["available"] is False
        assert body["summary"] == ""
        assert body["char_count"] == 0
        assert missing_source.status_code == 404


def test_stage_six_local_artifact_storage_reads_and_writes_text(tmp_path):
    storage = LocalArtifactStorage(tmp_path)

    artifact = storage.put_text("snapshots/task_1/source_1.html", "<html><p>Hello</p></html>")

    assert artifact.object_key == "snapshots/task_1/source_1.html"
    assert storage.read_text("snapshots/task_1/source_1.html") == "<html><p>Hello</p></html>"


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


def test_stage_six_search_index_rebuild_reports_index_counts(monkeypatch):
    monkeypatch.setattr(
        search_indexing.ElasticsearchIndexer,
        "rebuild_task",
        lambda self, db, task_id: search_indexing.SearchIndexSyncSummary(sources_indexed=2, evidence_indexed=5, failed_sources=0),
    )

    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        created = client.post(
            "/v1/research-tasks",
            json={
                "title": "Index rebuild smoke test",
                "prompt": "Research Cursor search index rebuild smoke test",
                "competitors": ["Cursor"],
                "dimensions": ["workflow"],
            },
        )
        assert created.status_code == 201
        task_id = created.json()["id"]

        response = client.post(f"/v1/research-tasks/{task_id}/search-index/rebuild")

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == task_id
    assert body["sources_indexed"] == 2
    assert body["evidence_indexed"] == 5
    assert body["failed_sources"] == 0
    assert body["index_backend"] == "elasticsearch"


def test_stage_six_search_endpoint_filters_task_scope_and_source_type():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        created = client.post(
            "/v1/research-tasks",
            json={
                "title": "Search endpoint smoke test",
                "prompt": "Research Cursor search endpoint smoke test",
                "competitors": ["Cursor"],
                "dimensions": ["pricing", "workflow"],
            },
        )
        assert created.status_code == 201
        task_id = created.json()["id"]

        db = SessionLocal()
        try:
            task = db.get(models.ResearchTask, task_id)
            assert task is not None
            docs_source = models.Source(
                task_id=task.id,
                url="https://cursor.example/docs",
                canonical_url="https://cursor.example/docs",
                source_type="docs",
                title="Cursor Docs",
                publisher="Cursor",
                content_hash="cursor-docs-hash",
                is_primary=True,
            )
            db.add(docs_source)
            db.flush()
            db.add(
                models.Evidence(
                    source_id=docs_source.id,
                    quote="Cursor docs mention pricing and workflow controls for teams.",
                    locator_json=research_service.encode_json({"kind": "html"}),
                    evidence_hash="cursor-docs-evidence",
                    extraction_method="manual_test",
                    quality_score=0.9,
                )
            )
            official_source = models.Source(
                task_id=task.id,
                url="https://cursor.example/pricing",
                canonical_url="https://cursor.example/pricing",
                source_type="official",
                title="Cursor Pricing",
                publisher="Cursor",
                content_hash="cursor-official-hash",
                is_primary=True,
            )
            db.add(official_source)
            db.flush()
            db.add(
                models.Evidence(
                    source_id=official_source.id,
                    quote="Cursor pricing page documents team billing and admin controls.",
                    locator_json=research_service.encode_json({"kind": "html"}),
                    evidence_hash="cursor-official-evidence",
                    extraction_method="manual_test",
                    quality_score=0.85,
                )
            )
            db.commit()
        finally:
            db.close()

        response = client.get(
            "/v1/search",
            params={
                "q": "Cursor",
                "task_id": task_id,
                "competitor": "Cursor",
                "dimension": "pricing",
                "source_type": "docs",
                "limit": 10,
            },
        )

    assert response.status_code == 200
    hits = response.json()
    assert hits
    assert all(hit["source_type"] == "docs" for hit in hits)
    assert all(hit["task_id"] == task_id for hit in hits)
    assert any(hit["kind"] == "evidence" for hit in hits)

    get_settings.cache_clear()


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
    assert prod_settings.database_url == "mysql+pymysql://verda:verda@mysql:3306/verda"
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
        assert settings.database_url == "mysql+pymysql://research:secret@10.10.0.12:3307/verda_prod"
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


def test_stage_one_contracts():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")

        invalid = client.post("/v1/research-tasks", json={"prompt": "太短"})
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "validation_error"

        first = client.post(
            "/v1/research-tasks",
            json={
                "title": "AI 编程工具阶段一验收",
                "prompt": "调研 Trae、Cursor、GitHub Copilot、Windsurf 的竞争格局",
                "competitors": ["Trae", "Cursor"],
                "dimensions": ["产品定位", "定价策略"],
            },
        )
        assert first.status_code == 201
        task_id = first.json()["id"]

        listed = client.get("/v1/research-tasks", params={"q": "阶段一", "limit": 1})
        assert listed.status_code == 200
        assert len(listed.json()) == 1
        assert listed.json()[0]["id"] == task_id

        confirmed = client.post(f"/v1/research-tasks/{task_id}/confirm")
        assert confirmed.status_code == 200
        assert confirmed.json()["error_message"] is None

        duplicate_confirm = client.post(f"/v1/research-tasks/{task_id}/confirm")
        assert duplicate_confirm.status_code == 409
        assert duplicate_confirm.json()["error"]["code"] == "task_not_confirmable"

        detail = client.get(f"/v1/research-tasks/{task_id}").json()
        claim = next(item for item in detail["claims"] if item["status"] == "conflict")
        reviewed = client.post(f"/v1/claims/{claim['id']}/review", json={"decision": "accept", "reason": "采用可信来源"})
        assert reviewed.status_code == 201

        reviewed_detail = client.get(f"/v1/research-tasks/{task_id}").json()
        reviewed_claim = next(item for item in reviewed_detail["claims"] if item["id"] == claim["id"])
        assert reviewed_claim["review_decision"] == "accept"
        assert reviewed_claim["status"] == "verified"

        reset = client.delete("/v1/dev/demo-data")
        assert reset.status_code == 200
        assert reset.json()["deleted_tasks"] >= 1
        assert client.get("/v1/research-tasks").json() == []


def test_review_workflow_completes_after_risky_claims_are_resolved():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        created = client.post(
            "/v1/research-tasks",
            json={
                "title": "人工审核闭环验收",
                "prompt": "调研 Trae、Cursor、GitHub Copilot、Windsurf 的竞争格局",
                "competitors": ["Trae", "Cursor", "Windsurf"],
                "dimensions": ["product positioning", "pricing strategy", "risk"],
            },
        )
        assert created.status_code == 201
        task_id = created.json()["id"]

        run = client.post(f"/v1/research-tasks/{task_id}/confirm")
        assert run.status_code == 200
        assert run.json()["status"] == "waiting_review"

        detail = client.get(f"/v1/research-tasks/{task_id}").json()
        risky_claims = [
            claim
            for claim in detail["claims"]
            if claim["status"] in {"conflict", "low_confidence", "undisclosed", "needs_evidence"}
        ]
        assert len(risky_claims) >= 2

        first = risky_claims[0]
        continue_response = client.post(
            f"/v1/claims/{first['id']}/review",
            json={"decision": "continue_research", "reason": "need more primary evidence"},
        )
        assert continue_response.status_code == 201

        after_continue = client.get(f"/v1/research-tasks/{task_id}").json()
        assert after_continue["task"]["status"] == "waiting_review"
        continued_claim = next(claim for claim in after_continue["claims"] if claim["id"] == first["id"])
        assert continued_claim["review_decision"] == "continue_research"

        rerun = client.post(f"/v1/research-tasks/{task_id}/runs")
        assert rerun.status_code == 201
        assert rerun.json()["status"] == "waiting_review"

        detail = client.get(f"/v1/research-tasks/{task_id}").json()
        unresolved_risky_claims = [
            claim
            for claim in detail["claims"]
            if claim["status"] in {"conflict", "low_confidence", "undisclosed", "needs_evidence"}
            and claim["review_decision"] != "exclude"
        ]
        assert unresolved_risky_claims

        for claim in unresolved_risky_claims:
            decision = "exclude" if claim["status"] == "conflict" else "accept"
            response = client.post(
                f"/v1/claims/{claim['id']}/review",
                json={"decision": decision, "reason": "manual review completed"},
            )
            assert response.status_code == 201

        completed = client.get(f"/v1/research-tasks/{task_id}").json()
        assert completed["task"]["status"] == "completed"
        assert completed["latest_run"]["status"] == "completed"

        events = client.get(f"/v1/research-tasks/{task_id}/events").json()
        event_types = [event["type"] for event in events]
        assert "review.decision_created" in event_types
        assert "task.completed" in event_types


def test_stage_five_review_completion_generates_next_report_version():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        created = client.post(
            "/v1/research-tasks",
            json={
                "title": "Review completion report regeneration",
                "prompt": "Research Trae, Cursor, GitHub Copilot, and Windsurf pricing and risk",
                "competitors": ["Trae", "Cursor", "Windsurf"],
                "dimensions": ["pricing strategy", "risk"],
            },
        )
        assert created.status_code == 201
        task_id = created.json()["id"]

        run = client.post(f"/v1/research-tasks/{task_id}/confirm")
        assert run.status_code == 200

        detail = client.get(f"/v1/research-tasks/{task_id}").json()
        assert [report["version"] for report in detail["reports"]] == [1]
        conflict_claim = next(claim for claim in detail["claims"] if claim["status"] == "conflict")
        undisclosed_claim = next(claim for claim in detail["claims"] if claim["status"] == "undisclosed")

        excluded = client.post(
            f"/v1/claims/{conflict_claim['id']}/review",
            json={"decision": "exclude", "reason": "source conflict"},
        )
        assert excluded.status_code == 201
        uncertain = client.post(
            f"/v1/claims/{undisclosed_claim['id']}/review",
            json={"decision": "mark_uncertain", "reason": "insufficient disclosure"},
        )
        assert uncertain.status_code == 201

        completed = client.get(f"/v1/research-tasks/{task_id}").json()
        assert completed["task"]["status"] == "completed"
        assert completed["latest_run"]["status"] == "completed"
        assert [report["version"] for report in completed["reports"]] == [1, 2]

        reviewed_claims = {claim["id"]: claim for claim in completed["claims"]}
        assert reviewed_claims[conflict_claim["id"]]["include_in_report"] is False
        assert reviewed_claims[undisclosed_claim["id"]]["include_in_report"] is True
        assert reviewed_claims[undisclosed_claim["id"]]["status"] == "low_confidence"

        latest_report = completed["reports"][-1]
        sections = {section["section_type"]: section["content_markdown"] for section in latest_report["sections"]}
        assert conflict_claim["display_text"] not in sections["key_claims"]
        assert undisclosed_claim["display_text"] in sections["key_claims"]
        assert undisclosed_claim["display_text"] in sections["review_risks"]

        events = client.get(f"/v1/research-tasks/{task_id}/events").json()
        report_events = [event for event in events if event["type"] == "report.created"]
        assert report_events[-1]["payload"]["version"] == 2
        assert report_events[-1]["stage"] == "generate_report"


def test_stage_eight_end_to_end_flow_covers_background_run_review_and_export():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        created = client.post(
            "/v1/research-tasks",
            json={
                "title": "Stage 8 end to end flow",
                "prompt": "Research Trae, Cursor, GitHub Copilot, and Windsurf end to end",
                "competitors": ["Trae", "Cursor", "GitHub Copilot", "Windsurf"],
                "dimensions": ["pricing strategy", "risk"],
            },
        )
        assert created.status_code == 201
        task_id = created.json()["id"]

        run = client.post(f"/v1/research-tasks/{task_id}/confirm?background=true")
        assert run.status_code == 200
        assert run.json()["status"] == models.RunStatus.queued.value

        detail = client.get(f"/v1/research-tasks/{task_id}").json()
        assert detail["task"]["status"] == models.TaskStatus.waiting_review.value
        assert detail["latest_run"]["status"] == models.RunStatus.waiting_review.value
        assert detail["reports"]
        assert [report["version"] for report in detail["reports"]] == [1]

        risky_claims = [claim for claim in detail["claims"] if claim["status"] in {"conflict", "undisclosed", "low_confidence", "needs_evidence"}]
        assert risky_claims
        for claim in risky_claims:
            decision = "exclude" if claim["status"] == "conflict" else "accept"
            reviewed = client.post(
                f"/v1/claims/{claim['id']}/review",
                json={"decision": decision, "reason": "end to end flow review"},
            )
            assert reviewed.status_code == 201

        completed = client.get(f"/v1/research-tasks/{task_id}").json()
        assert completed["task"]["status"] == models.TaskStatus.completed.value
        assert completed["latest_run"]["status"] == models.RunStatus.completed.value
        assert [report["version"] for report in completed["reports"]] == [1, 2]

        latest_report = completed["reports"][-1]
        exported = client.post(f"/v1/reports/{latest_report['id']}/export?format=markdown")
        assert exported.status_code == 200
        content = exported.json()["content"]
        assert content.startswith("## ")
        assert "##" in content

        events = client.get(f"/v1/research-tasks/{task_id}/events").json()
        event_types = [event["type"] for event in events]
        assert "review.decision_created" in event_types
        assert event_types[-1] == "task.completed"
def test_stage_two_state_machine_and_traceability_contracts():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")

        created = client.post(
            "/v1/research-tasks",
            json={
                "title": "Stage 2 state machine traceability",
                "prompt": "Research Trae, Cursor, GitHub Copilot, and Windsurf",
                "competitors": ["Trae", "Cursor"],
                "dimensions": ["product positioning", "pricing strategy"],
            },
        )
        assert created.status_code == 201
        task = created.json()
        assert task["status"] == "draft"
        assert task["current_run_id"] is None
        assert task["confirmed_at"] is None

        run = client.post(f"/v1/research-tasks/{task['id']}/confirm")
        assert run.status_code == 200
        run_body = run.json()
        assert run_body["status"] == "waiting_review"
        assert run_body["input_snapshot"]["competitors"] == ["Trae", "Cursor"]
        assert run_body["queued_at"] is not None

        detail = client.get(f"/v1/research-tasks/{task['id']}").json()
        assert detail["task"]["status"] == "waiting_review"
        assert detail["task"]["current_run_id"] == run_body["id"]
        assert detail["task"]["confirmed_at"] is not None
        assert detail["task"]["queued_at"] is not None
        assert detail["latest_run"]["input_snapshot"]["dimensions"] == ["product positioning", "pricing strategy"]
        assert any(source["is_primary"] for source in detail["sources"])
        assert all(evidence["evidence_hash"] for evidence in detail["evidence"])
        assert all(evidence["extraction_method"] for evidence in detail["evidence"])
        assert all("dimension" in claim for claim in detail["claims"])
        assert all("evidence_coverage" in claim for claim in detail["claims"])
        assert detail["reports"][0]["input_snapshot"]["report_depth"] == "standard"
        assert detail["reports"][0]["generated_at"] is not None

        conflict_claim = next(item for item in detail["claims"] if item["status"] == "conflict")
        reviewed = client.post(f"/v1/claims/{conflict_claim['id']}/review", json={"decision": "accept", "reason": "采用可信来源"})
        assert reviewed.status_code == 201
        assert reviewed.json()["previous_status"] == "conflict"
        assert reviewed.json()["resulting_status"] == "verified"

        duplicate_confirm = client.post(f"/v1/research-tasks/{task['id']}/confirm")
        assert duplicate_confirm.status_code == 409
        assert duplicate_confirm.json()["error"]["code"] == "task_not_confirmable"


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


def test_stage_four_report_template_includes_review_and_reference_sections(monkeypatch, tmp_path):
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
        summary = collection.collect_research_evidence(
            db,
            task=task,
            run=run,
            settings=Settings(search_provider="test", artifact_storage_dir=str(tmp_path), min_source_text_chars=120),
            write_event=lambda event_type, stage, message, payload=None: None,
        )
        claim_extractor.extract_and_store_claims(
            db,
            task=task,
            settings=Settings(search_provider="test", artifact_storage_dir=str(tmp_path), llm_max_evidence_items=4),
        )

        collection.create_claim_report(db, task, summary)

        report = db.query(models.Report).filter_by(task_id=task.id).one()
        sections = {section.section_type: section for section in report.sections}
        assert list(sections) == ["executive_summary", "collection_summary", "key_claims", "review_risks", "citation_coverage"]
        assert "Evidence" in sections["key_claims"].content_markdown
        assert "100%" in sections["citation_coverage"].content_markdown
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

        def flaky_create_claim_report(db, task, summary):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("temporary report renderer failure")
            return original_create_claim_report(db, task, summary)

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


def test_stage_five_workflow_entry_runs_complete_research_flow():
    from app.workflows.research_graph import run_research_workflow

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor and GitHub Copilot enterprise positioning",
                competitors=["Cursor", "GitHub Copilot"],
                dimensions=["pricing", "enterprise controls"],
            ),
        )
        run = research_service.create_run(db, task.id)

        result = run_research_workflow(db, run.id)

        assert result.status == models.RunStatus.waiting_review.value
        assert result.current_stage == "review_gate"
        assert db.query(models.Source).filter_by(task_id=task.id).count() >= 3
        assert db.query(models.Evidence).join(models.Source).filter(models.Source.task_id == task.id).count() >= 3
        assert db.query(models.Claim).filter_by(task_id=task.id).count() >= 3
        assert db.query(models.Report).filter_by(task_id=task.id).count() == 1
        domain_event_types = [
            event.type
            for event in db.query(models.ResearchEvent).filter_by(run_id=run.id).order_by(models.ResearchEvent.sequence_no)
            if not event.type.startswith("node.")
        ]
        assert domain_event_types == [
            "planning.started",
            "search.skipped",
            "search.started",
            "source.found",
            "evidence.created",
            "claim.created",
            "review.required",
            "report.created",
        ]
    finally:
        db.rollback()
        db.close()


def test_stage_five_workflow_completes_when_review_gate_has_no_risky_claims(monkeypatch):
    from app.workflows.research_graph import run_research_workflow

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor verified-only workflow completion",
                competitors=["Cursor"],
                dimensions=["enterprise controls"],
            ),
        )
        run = research_service.create_run(db, task.id)

        def seed_verified_evidence(db, task, discovery, parsed_sources, write_event):
            source = models.Source(
                task_id=task.id,
                url="https://cursor.example/security",
                canonical_url="https://cursor.example/security",
                source_type="official",
                title="Cursor Security",
                publisher="Cursor",
                content_hash=f"{task.id}-verified-source",
                is_primary=True,
            )
            db.add(source)
            db.flush()
            evidence = models.Evidence(
                source_id=source.id,
                quote="Cursor enterprise controls include policy management and audit-oriented administration.",
                locator_json=research_service.encode_json({"kind": "html", "heading": "Security"}),
                evidence_hash=f"{source.id}-verified-evidence",
                extraction_method="verified_only_test",
                quality_score=0.9,
            )
            db.add(evidence)
            db.commit()
            write_event(
                "evidence.created",
                "extract_evidence",
                "Seeded verified-only evidence for review gate completion.",
                {"evidence_created": 1},
            )
            return collection.CollectionSummary(
                provider="test",
                searched=False,
                source_candidates=1,
                sources_created=1,
                evidence_created=1,
            )

        monkeypatch.setattr(research_service, "extract_research_evidence", seed_verified_evidence)

        result = run_research_workflow(db, run.id)

        assert result.status == models.RunStatus.completed.value
        assert result.current_stage == "completed"
        db.refresh(task)
        assert task.status == models.TaskStatus.completed.value
        assert db.query(models.Report).filter_by(task_id=task.id).count() == 1
        event_types = [
            event.type
            for event in db.query(models.ResearchEvent).filter_by(run_id=run.id).order_by(models.ResearchEvent.sequence_no)
            if not event.type.startswith("node.")
        ]
        assert "review.required" not in event_types
        assert event_types[-1] == "task.completed"
    finally:
        db.rollback()
        db.close()


def test_stage_five_review_gate_emits_review_required_for_risky_real_claims(monkeypatch):
    from app.workflows.research_graph import run_research_workflow

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor risky workflow review signal",
                competitors=["Cursor"],
                dimensions=["pricing"],
            ),
        )
        run = research_service.create_run(db, task.id)

        def seed_evidence(db, task, discovery, parsed_sources, write_event):
            source = models.Source(
                task_id=task.id,
                url="https://cursor.example/pricing",
                canonical_url="https://cursor.example/pricing",
                source_type="official",
                title="Cursor Pricing",
                publisher="Cursor",
                content_hash=f"{task.id}-risky-source",
                is_primary=True,
            )
            db.add(source)
            db.flush()
            evidence = models.Evidence(
                source_id=source.id,
                quote="Cursor pricing information conflicts across official and partner pages.",
                locator_json=research_service.encode_json({"kind": "html", "heading": "Pricing"}),
                evidence_hash=f"{source.id}-risky-evidence",
                extraction_method="risky_review_signal_test",
                quality_score=0.88,
            )
            db.add(evidence)
            db.commit()
            return collection.CollectionSummary(
                provider="test",
                searched=True,
                source_candidates=1,
                sources_created=1,
                evidence_created=1,
            )

        def seed_conflict_claim(db, task, settings):
            evidence = db.query(models.Evidence).join(models.Source).filter(models.Source.task_id == task.id).one()
            claim = models.Claim(
                task_id=task.id,
                subject="Cursor",
                predicate="has_conflicting_price",
                value_json=research_service.encode_json({"conflict": True}),
                claim_type="pricing",
                dimension="pricing",
                status=models.ClaimStatus.conflict.value,
                confidence="conflict",
                confidence_score=0.5,
                display_text="Cursor pricing has conflicting source claims.",
                evidence_coverage=1.0,
            )
            db.add(claim)
            db.flush()
            db.add(models.ClaimEvidence(claim_id=claim.id, evidence_id=evidence.id, relation="conflicts", weight=1.0))
            db.commit()
            return claim_extractor.ClaimExtractionResult(claims=[])

        monkeypatch.setattr(research_service, "extract_research_evidence", seed_evidence)
        monkeypatch.setattr(research_service, "extract_and_store_claims", seed_conflict_claim)

        result = run_research_workflow(db, run.id)

        assert result.status == models.RunStatus.waiting_review.value
        assert result.current_stage == "review_gate"
        event_types = [
            event.type
            for event in db.query(models.ResearchEvent).filter_by(run_id=run.id).order_by(models.ResearchEvent.sequence_no)
            if not event.type.startswith("node.")
        ]
        assert "review.required" in event_types
    finally:
        db.rollback()
        db.close()


def test_stage_five_workflow_continues_when_one_source_fetch_fails(monkeypatch):
    from app.workflows.research_graph import run_research_workflow

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
        run = research_service.create_run(db, task.id)

        def fake_discover_research_sources(*args, **kwargs):
            return collection.SourceDiscovery(
                scope=research_service.decode_json(task.scope_json),
                query="Cursor pricing enterprise controls",
                results=[
                    SearchResult(title="Broken Cursor mirror", url="https://broken.example/cursor", source_type="web"),
                    SearchResult(title="Cursor official docs", url="https://cursor.example/security", source_type="official", score=0.92),
                ],
                summary=collection.CollectionSummary(provider="test", searched=True, source_candidates=2),
            )

        class FakeFetcher:
            def __init__(self, **kwargs) -> None:
                pass

            def fetch(self, url: str) -> FetchResult:
                if "broken.example" in url:
                    raise fetcher_module.WebFetchError("temporary upstream failure")
                return FetchResult(
                    url=url,
                    final_url=url,
                    content_type="text/html",
                    status_code=200,
                    html=(
                        "<html><head><title>Cursor Enterprise Controls</title></head><body>"
                        "<p>Cursor pricing and enterprise controls are documented for teams with policy management, "
                        "shared workspace administration, audit support, security review, and procurement workflows. "
                        "These details give buyers enough public evidence to compare Cursor against other coding assistants. "
                        "The documentation describes team administration, centralized billing, source control permissions, "
                        "privacy settings, compliance review, enterprise onboarding, and repeatable purchasing workflows. "
                        "Cursor positions these controls as part of a mature product workflow for organizations that need "
                        "pricing clarity, user governance, audit trails, and secure AI coding assistance across many teams.</p>"
                        "</body></html>"
                    ),
                )

        monkeypatch.setattr(research_service, "discover_research_sources", fake_discover_research_sources)
        monkeypatch.setattr(collection, "HttpPageFetcher", FakeFetcher)

        result = run_research_workflow(db, run.id)

        assert result.status == models.RunStatus.completed.value
        assert result.current_stage == "completed"
        assert db.query(models.Source).filter_by(task_id=task.id).count() == 1
        assert db.query(models.Evidence).join(models.Source).filter(models.Source.task_id == task.id).count() >= 1
        assert db.query(models.Report).filter_by(task_id=task.id).count() == 1

        events = db.query(models.ResearchEvent).filter_by(run_id=run.id).order_by(models.ResearchEvent.sequence_no).all()
        assert any(event.type == "source.fetch_failed" for event in events)
        assert not any(event.type == "node.failed" for event in events)
    finally:
        db.rollback()
        db.close()


def test_stage_five_workflow_emits_fetch_exhausted_when_all_candidates_fail(monkeypatch):
    from app.workflows.research_graph import run_research_workflow

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
        run = research_service.create_run(db, task.id)

        def fake_discover_research_sources(*args, **kwargs):
            return collection.SourceDiscovery(
                scope=research_service.decode_json(task.scope_json),
                query="Cursor pricing enterprise controls",
                results=[
                    SearchResult(title="Broken Cursor mirror", url="https://broken.example/cursor", source_type="web"),
                    SearchResult(title="Another broken Cursor mirror", url="https://broken2.example/cursor", source_type="web"),
                ],
                summary=collection.CollectionSummary(provider="test", searched=True, source_candidates=2),
            )

        class FakeFetcher:
            def __init__(self, **kwargs) -> None:
                pass

            def fetch(self, url: str) -> FetchResult:
                raise fetcher_module.WebFetchError(f"temporary upstream failure for {url}")

        monkeypatch.setattr(research_service, "discover_research_sources", fake_discover_research_sources)
        monkeypatch.setattr(collection, "HttpPageFetcher", FakeFetcher)
        monkeypatch.setattr(
            research_service,
            "extract_and_store_claims",
            lambda *args, **kwargs: claim_extractor.ClaimExtractionResult(claims=[]),
        )

        result = run_research_workflow(db, run.id)

        assert result.status == models.RunStatus.waiting_review.value
        assert result.current_stage == "review_gate"
        assert db.query(models.Source).filter_by(task_id=task.id).count() == 3
        assert db.query(models.Report).filter_by(task_id=task.id).count() == 1

        events = db.query(models.ResearchEvent).filter_by(run_id=run.id).order_by(models.ResearchEvent.sequence_no).all()
        assert [event.type for event in events if event.type == "source.fetch_failed"] == [
            "source.fetch_failed",
            "source.fetch_failed",
        ]
        assert any(event.type == "source.fetch_exhausted" for event in events)
        assert not any(event.type == "node.failed" for event in events)
    finally:
        db.rollback()
        db.close()


def test_stage_five_workflow_emits_parse_exhausted_when_all_fetched_pages_are_low_quality(monkeypatch):
    from app.workflows.research_graph import run_research_workflow

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
        run = research_service.create_run(db, task.id)

        def fake_discover_research_sources(*args, **kwargs):
            return collection.SourceDiscovery(
                scope=research_service.decode_json(task.scope_json),
                query="Cursor pricing enterprise controls",
                results=[
                    SearchResult(title="Thin Cursor page", url="https://thin.example/cursor", source_type="web"),
                    SearchResult(title="Another thin Cursor page", url="https://thin2.example/cursor", source_type="web"),
                ],
                summary=collection.CollectionSummary(provider="test", searched=True, source_candidates=2),
            )

        class FakeFetcher:
            def __init__(self, **kwargs) -> None:
                pass

            def fetch(self, url: str) -> FetchResult:
                return FetchResult(
                    url=url,
                    final_url=url,
                    content_type="text/html",
                    status_code=200,
                    html="<html><body><p>Too short.</p></body></html>",
                )

        monkeypatch.setattr(research_service, "discover_research_sources", fake_discover_research_sources)
        monkeypatch.setattr(collection, "HttpPageFetcher", FakeFetcher)

        result = run_research_workflow(db, run.id)

        assert result.status == models.RunStatus.waiting_review.value
        assert result.current_stage == "review_gate"
        assert db.query(models.Source).filter_by(task_id=task.id).count() == 3
        assert db.query(models.Report).filter_by(task_id=task.id).count() == 1

        events = db.query(models.ResearchEvent).filter_by(run_id=run.id).order_by(models.ResearchEvent.sequence_no).all()
        assert [event.type for event in events if event.type == "source.parse_skipped"] == [
            "source.parse_skipped",
            "source.parse_skipped",
        ]
        assert any(event.type == "source.parse_exhausted" for event in events)
        assert not any(event.type == "node.failed" for event in events)
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


def test_stage_five_workflow_state_carries_required_fields():
    from app.workflows.research_graph import ResearchWorkflowState

    state = ResearchWorkflowState(
        task_id="task-1",
        run_id="run-1",
        scope={"competitors": ["Cursor"]},
        summary={"evidence_created": 3},
        errors=[],
        current_node="review_gate",
    )

    assert state["task_id"] == "task-1"
    assert state["run_id"] == "run-1"
    assert state["scope"]["competitors"] == ["Cursor"]
    assert state["summary"]["evidence_created"] == 3
    assert state["errors"] == []
    assert state["current_node"] == "review_gate"


def test_stage_five_missing_langgraph_dependency_has_clear_error(monkeypatch):
    from app.workflows import research_graph

    monkeypatch.setattr(research_graph, "StateGraph", None)

    with pytest.raises(RuntimeError, match="LangGraph is required.*pip install"):
        research_graph.build_research_graph()


def test_stage_five_checkpoint_cleanup_keeps_latest_recovery_path(monkeypatch):
    from app.workflows import research_graph

    monkeypatch.setattr(research_graph, "MAX_CHECKPOINTS_PER_RUN", 2, raising=False)

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor checkpoint cleanup",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        run = research_service.create_run(db, task.id)
        base_state = {
            "task_id": task.id,
            "run_id": run.id,
            "scope": research_service.decode_json(task.scope_json),
            "summary": {"current_node": "initialize_run"},
            "errors": [],
            "current_node": "initialize_run",
        }

        for _ in range(3):
            research_graph.save_success_checkpoint(
                db,
                run_id=run.id,
                node_name="initialize_run",
                input_summary={"stage": "initialize_run"},
                output_summary={"current_node": "plan_research"},
                state=base_state,
                result={"current_node": "plan_research", "summary": {"run_status": models.RunStatus.running.value, "current_stage": "plan_research"}},
            )

        research_graph.save_failed_checkpoint(
            db,
            run_id=run.id,
            node_name="plan_research",
            input_summary={"stage": "plan_research"},
            retryable=True,
            error="temporary planning failure",
            state={
                **base_state,
                "summary": {"current_node": "plan_research", "run_status": models.RunStatus.failed.value, "current_stage": "plan_research"},
                "current_node": "plan_research",
            },
        )

        checkpoints = (
            db.query(models.WorkflowCheckpoint)
            .filter_by(run_id=run.id)
            .order_by(models.WorkflowCheckpoint.sequence_no.asc())
            .all()
        )

        assert len(checkpoints) == 2
        assert [checkpoint.status for checkpoint in checkpoints] == ["succeeded", "failed"]
        assert checkpoints[-1].resume_node == "plan_research"
        assert research_graph.latest_success_checkpoint(db, run.id).sequence_no == checkpoints[0].sequence_no
    finally:
        db.rollback()
        db.close()


def test_stage_five_workflow_emits_node_lifecycle_events():
    from app.workflows.research_graph import run_research_workflow

    expected_nodes = [
        "initialize_run",
        "plan_research",
        "build_search_plan",
        "discover_sources",
        "fetch_sources",
        "parse_sources",
        "extract_evidence",
        "extract_claims",
        "verify_claims",
        "generate_report",
        "review_gate",
    ]

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor workflow observability",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        run = research_service.create_run(db, task.id)

        run_research_workflow(db, run.id)

        lifecycle_events = (
            db.query(models.ResearchEvent)
            .filter(models.ResearchEvent.run_id == run.id, models.ResearchEvent.type.in_(["node.started", "node.succeeded"]))
            .order_by(models.ResearchEvent.sequence_no)
            .all()
        )
        assert [event.stage for event in lifecycle_events] == [node for node in expected_nodes for _ in range(2)]
        assert [event.type for event in lifecycle_events] == ["node.started", "node.succeeded"] * len(expected_nodes)

        started_payload = research_service.decode_json(lifecycle_events[0].payload_json)
        assert lifecycle_events[0].stage == "initialize_run"
        assert started_payload["stage"] == "initialize_run"
        assert started_payload["node_name"] == "initialize_run"
        assert started_payload["duration_ms"] == 0
        assert started_payload["input_summary"] == {
            "task_id": task.id,
            "run_id": run.id,
            "competitors_count": 1,
            "dimensions_count": 1,
        }
        assert started_payload["output_summary"] == {}

        succeeded_payload = research_service.decode_json(lifecycle_events[1].payload_json)
        assert succeeded_payload["node_name"] == "initialize_run"
        assert succeeded_payload["duration_ms"] >= 0
        assert succeeded_payload["input_summary"]["run_id"] == run.id
        assert succeeded_payload["output_summary"] == {
            "current_node": "plan_research",
            "run_status": models.RunStatus.running.value,
            "current_stage": "plan_research",
        }

        final_payload = research_service.decode_json(lifecycle_events[-1].payload_json)
        assert final_payload["node_name"] == "review_gate"
        assert final_payload["output_summary"]["current_node"] == "review_gate"
        assert final_payload["output_summary"]["run_status"] == models.RunStatus.waiting_review.value
        assert final_payload["output_summary"]["current_stage"] == "review_gate"
    finally:
        db.rollback()
        db.close()


def test_stage_five_workflow_passes_search_plan_into_source_discovery(monkeypatch):
    from app.workflows.research_graph import run_research_workflow

    captured: dict[str, object] = {}

    def fake_discover_research_sources(db, *, task, settings, write_event, search_plan=None):
        captured["search_plan"] = search_plan
        return collection.SourceDiscovery(
            scope=research_service.decode_json(task.scope_json),
            query=search_plan["query"] if search_plan else "",
            results=[],
            summary=collection.CollectionSummary(provider="test"),
        )

    monkeypatch.setattr(research_service, "discover_research_sources", fake_discover_research_sources)

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor enterprise controls using https://prompt.example/source",
                competitors=["Cursor"],
                dimensions=["security"],
                source_preferences=["https://manual.example/source"],
            ),
        )
        run = research_service.create_run(db, task.id)

        run_research_workflow(db, run.id)

        search_plan = captured["search_plan"]
        assert search_plan["query"] == "Research Cursor enterprise controls using https://prompt.example/source Cursor security"
        assert search_plan["source_preferences"] == ["https://manual.example/source"]
    finally:
        db.rollback()
        db.close()


def test_stage_five_discovery_uses_search_plan_query_and_manual_url_priority(monkeypatch):
    captured: dict[str, object] = {}

    class CapturingSearchAdapter:
        def search(self, query: str, *, max_results: int) -> list[SearchResult]:
            captured["query"] = query
            captured["max_results"] = max_results
            return []

    def fake_build_search_adapter(settings, manual_urls):
        captured["manual_urls"] = manual_urls
        return CapturingSearchAdapter()

    monkeypatch.setattr(collection, "build_search_adapter", fake_build_search_adapter)

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor security using https://prompt.example/source",
                competitors=["Cursor"],
                dimensions=["security"],
            ),
        )

        discovery = collection.discover_research_sources(
            db,
            task=task,
            settings=Settings(search_provider="test", search_max_results=5),
            write_event=lambda event_type, stage, message, payload=None: None,
            search_plan={
                "query": "planned Cursor security query",
                "source_preferences": ["https://manual.example/source", "https://prompt.example/source"],
            },
        )

        assert captured["query"] == "planned Cursor security query"
        assert captured["manual_urls"] == ["https://manual.example/source", "https://prompt.example/source"]
        assert discovery.query == "planned Cursor security query"
    finally:
        db.rollback()
        db.close()


def test_stage_five_discovery_uses_search_plan_budget_and_source_priority(monkeypatch):
    captured: dict[str, object] = {}

    class PrioritySearchAdapter:
        def search(self, query: str, *, max_results: int) -> list[SearchResult]:
            captured["query"] = query
            captured["max_results"] = max_results
            return [
                SearchResult(title="News", url="https://news.example/article", score=0.82, source_type="news"),
                SearchResult(title="Docs", url="https://docs.example/page", score=0.91, source_type="docs"),
                SearchResult(title="Official", url="https://official.example/pricing", score=0.74, source_type="official"),
            ]

    def fake_build_search_adapter(settings, manual_urls):
        captured["manual_urls"] = manual_urls
        return PrioritySearchAdapter()

    monkeypatch.setattr(collection, "build_search_adapter", fake_build_search_adapter)

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor security controls",
                competitors=["Cursor"],
                dimensions=["security"],
                source_preferences=["https://manual.example/source"],
            ),
        )

        discovery = collection.discover_research_sources(
            db,
            task=task,
            settings=Settings(search_provider="test", search_max_results=5),
            write_event=lambda event_type, stage, message, payload=None: None,
            search_plan={
                "query": "planned Cursor security query",
                "budget": {"max_candidate_sources": 2},
                "source_type_priority": ["official", "docs", "news", "web"],
                "source_preferences": ["https://manual.example/source"],
            },
        )

        assert captured["query"] == "planned Cursor security query"
        assert captured["max_results"] == 2
        assert [result.source_type for result in discovery.results] == ["official", "docs"]
    finally:
        db.rollback()
        db.close()


def test_stage_five_workflow_emits_node_failed_event(monkeypatch):
    from app.workflows import research_graph

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor workflow failure observability",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        run = research_service.create_run(db, task.id)

        def fail_fetch_sources(*args, **kwargs):
            raise RuntimeError("workflow node exploded")

        monkeypatch.setattr(research_service, "fetch_research_sources", fail_fetch_sources, raising=False)

        with pytest.raises(RuntimeError, match="workflow node exploded"):
            research_graph.run_research_workflow(db, run.id)

        failed_event = db.query(models.ResearchEvent).filter_by(run_id=run.id, type="node.failed").one()
        assert failed_event.stage == "fetch_sources"
        assert failed_event.severity == "error"
        payload = research_service.decode_json(failed_event.payload_json)
        assert payload["stage"] == "fetch_sources"
        assert payload["node_name"] == "fetch_sources"
        assert payload["duration_ms"] >= 0
        assert payload["input_summary"]["run_id"] == run.id
        assert payload["output_summary"] == {}
        assert payload["error"] == "workflow node exploded"
    finally:
        db.rollback()
        db.close()


def test_stage_five_workflow_saves_success_checkpoints():
    from app.workflows.research_graph import run_research_workflow

    expected_nodes = [
        "initialize_run",
        "plan_research",
        "build_search_plan",
        "discover_sources",
        "fetch_sources",
        "parse_sources",
        "extract_evidence",
        "extract_claims",
        "verify_claims",
        "generate_report",
        "review_gate",
    ]

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor checkpoint observability",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        run = research_service.create_run(db, task.id)

        run_research_workflow(db, run.id)

        checkpoints = db.query(models.WorkflowCheckpoint).filter_by(run_id=run.id).order_by(models.WorkflowCheckpoint.sequence_no).all()
        assert [checkpoint.node_name for checkpoint in checkpoints] == expected_nodes
        assert [checkpoint.status for checkpoint in checkpoints] == ["succeeded"] * len(expected_nodes)
        assert checkpoints[0].resume_node == "plan_research"
        assert checkpoints[-1].resume_node == "review_gate"

        final_state = research_service.decode_json(checkpoints[-1].state_json)
        assert final_state["task_id"] == task.id
        assert final_state["run_id"] == run.id
        assert final_state["current_node"] == "review_gate"
        assert final_state["summary"]["run_status"] == models.RunStatus.waiting_review.value
    finally:
        db.rollback()
        db.close()


def test_stage_five_workflow_resumes_from_latest_success_checkpoint(monkeypatch):
    from app.workflows import research_graph

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor checkpoint resume",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        run = research_service.create_run(db, task.id)

        original_verify_claims = research_service.verify_claims
        calls = {"count": 0}

        def fail_once_verify_claims(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("temporary verification failure")
            return original_verify_claims(*args, **kwargs)

        monkeypatch.setattr(research_service, "verify_claims", fail_once_verify_claims)

        with pytest.raises(RuntimeError, match="temporary verification failure"):
            research_graph.run_research_workflow(db, run.id)

        failed_run = db.get(models.TaskRun, run.id)
        assert failed_run is not None
        assert failed_run.status == models.RunStatus.failed.value
        assert failed_run.current_stage == "verify_claims"

        failed_checkpoint = (
            db.query(models.WorkflowCheckpoint)
            .filter_by(run_id=run.id, node_name="verify_claims", status="failed")
            .one()
        )
        assert failed_checkpoint.resume_node == "verify_claims"

        latest_checkpoint = (
            db.query(models.WorkflowCheckpoint)
            .filter_by(run_id=run.id, status="succeeded")
            .order_by(models.WorkflowCheckpoint.sequence_no.desc())
            .first()
        )
        assert latest_checkpoint is not None
        assert latest_checkpoint.node_name == "extract_claims"
        assert latest_checkpoint.resume_node == "verify_claims"

        resumed = research_graph.run_research_workflow(db, run.id, resume=True)

        assert resumed.status == models.RunStatus.waiting_review.value
        assert calls["count"] == 2
        assert db.query(models.Report).filter_by(task_id=task.id).count() == 1

        initialize_started = db.query(models.ResearchEvent).filter_by(run_id=run.id, type="node.started", stage="initialize_run").count()
        verify_started = db.query(models.ResearchEvent).filter_by(run_id=run.id, type="node.started", stage="verify_claims").count()
        assert initialize_started == 1
        assert verify_started == 2
    finally:
        db.rollback()
        db.close()


def test_stage_five_workflow_resumes_fetch_sources_from_serialized_discovery(monkeypatch):
    from app.workflows import research_graph

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor fetch resume recovery",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        run = research_service.create_run(db, task.id)
        fake_discovery = collection.SourceDiscovery(
            scope=research_service.decode_json(task.scope_json),
            query="Cursor workflow recovery",
            results=[SearchResult(title="Cursor", url="https://cursor.example/pricing", source_type="official")],
            summary=collection.CollectionSummary(provider="test"),
        )
        calls = {"count": 0}

        def fake_discover_research_sources(*args, **kwargs):
            return fake_discovery

        def fail_once_fetch_sources(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] <= 2:
                raise RuntimeError("temporary fetch failure")
            return []

        monkeypatch.setattr(research_service, "discover_research_sources", fake_discover_research_sources)
        monkeypatch.setattr(research_service, "fetch_research_sources", fail_once_fetch_sources)

        with pytest.raises(RuntimeError, match="temporary fetch failure"):
            research_graph.run_research_workflow(db, run.id)

        latest_success = (
            db.query(models.WorkflowCheckpoint)
            .filter_by(run_id=run.id, status="succeeded")
            .order_by(models.WorkflowCheckpoint.sequence_no.desc())
            .first()
        )
        assert latest_success is not None
        assert latest_success.node_name == "discover_sources"
        checkpoint_state = research_service.decode_json(latest_success.state_json)
        discovery_state = checkpoint_state["summary"]["collection_discovery_state"]
        assert discovery_state["query"] == "Cursor workflow recovery"
        assert discovery_state["results"][0]["url"] == "https://cursor.example/pricing"

        resumed = research_graph.run_research_workflow(db, run.id, resume=True)

        assert resumed.status == models.RunStatus.waiting_review.value
        assert resumed.current_stage == "review_gate"
        assert calls["count"] == 3
    finally:
        db.rollback()
        db.close()


def test_stage_five_workflow_resumes_parse_sources_from_serialized_fetches(monkeypatch):
    from app.workflows import research_graph

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor parse resume recovery",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        run = research_service.create_run(db, task.id)
        original_parse_sources = research_service.parse_research_sources
        calls = {"count": 0}

        def fake_discover_research_sources(*args, **kwargs):
            return collection.SourceDiscovery(
                scope=research_service.decode_json(task.scope_json),
                query="Cursor workflow recovery",
                results=[
                    SearchResult(title="Cursor", url="https://cursor.example/pricing", source_type="official"),
                ],
                summary=collection.CollectionSummary(provider="test"),
            )

        def fake_fetch_research_sources(*args, **kwargs):
            return [
                collection.FetchedSource(
                    result=SearchResult(title="Cursor", url="https://cursor.example/pricing", source_type="official"),
                    canonical_url="https://cursor.example/pricing",
                        fetched=FetchResult(
                            url="https://cursor.example/pricing",
                            final_url="https://cursor.example/pricing",
                            html=(
                                "<html><head><title>Cursor Pricing</title></head><body>"
                                "<p>Cursor workflow controls and pricing details are documented for enterprise teams with admin support, "
                                "including repository policy controls, shared workspace administration, audit logging, and procurement review. "
                                "These notes are intentionally long enough to survive the quality filter and behave like a real fetched page.</p>"
                                "</body></html>"
                            ),
                            content_type="text/html",
                            status_code=200,
                        ),
                )
            ]

        def fail_once_parse_sources(db, *, task, discovery, fetched_sources, settings, write_event):
            calls["count"] += 1
            if calls["count"] == 1:
                raise ValueError("parsed_sources_missing")
            assert fetched_sources
            return original_parse_sources(
                db,
                task=task,
                discovery=discovery,
                fetched_sources=fetched_sources,
                settings=settings,
                write_event=write_event,
            )

        monkeypatch.setattr(research_service, "discover_research_sources", fake_discover_research_sources)
        monkeypatch.setattr(research_service, "fetch_research_sources", fake_fetch_research_sources)
        monkeypatch.setattr(research_service, "parse_research_sources", fail_once_parse_sources)

        with pytest.raises(ValueError, match="parsed_sources_missing"):
            research_graph.run_research_workflow(db, run.id)

        latest_success = (
            db.query(models.WorkflowCheckpoint)
            .filter_by(run_id=run.id, status="succeeded")
            .order_by(models.WorkflowCheckpoint.sequence_no.desc())
            .first()
        )
        assert latest_success is not None
        assert latest_success.node_name == "fetch_sources"
        checkpoint_state = research_service.decode_json(latest_success.state_json)
        fetched_state = checkpoint_state["summary"]["fetched_sources_state"]
        assert fetched_state[0]["canonical_url"] == "https://cursor.example/pricing"

        resumed = research_graph.run_research_workflow(db, run.id, resume=True)

        assert resumed.status == models.RunStatus.waiting_review.value
        assert resumed.current_stage == "review_gate"
        assert calls["count"] == 2
    finally:
        db.rollback()
        db.close()


def test_stage_five_workflow_resumes_extract_evidence_from_serialized_parsed_sources(monkeypatch):
    from app.workflows import research_graph

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor evidence resume recovery",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        run = research_service.create_run(db, task.id)
        original_extract_evidence = research_service.extract_research_evidence
        calls = {"count": 0}

        def fake_discover_research_sources(*args, **kwargs):
            return collection.SourceDiscovery(
                scope=research_service.decode_json(task.scope_json),
                query="Cursor workflow recovery",
                results=[
                    SearchResult(title="Cursor", url="https://cursor.example/pricing", source_type="official"),
                ],
                summary=collection.CollectionSummary(provider="test"),
            )

        def fake_fetch_research_sources(*args, **kwargs):
            return [
                collection.FetchedSource(
                    result=SearchResult(title="Cursor", url="https://cursor.example/pricing", source_type="official"),
                    canonical_url="https://cursor.example/pricing",
                    fetched=FetchResult(
                        url="https://cursor.example/pricing",
                        final_url="https://cursor.example/pricing",
                        html=(
                            "<html><head><title>Cursor Pricing</title></head><body>"
                            "<p>Cursor workflow controls and pricing details are documented for enterprise teams with admin support, "
                            "including repository policy controls, shared workspace administration, audit logging, and procurement review. "
                            "These notes are intentionally long enough to survive the quality filter and behave like a real fetched page.</p>"
                            "</body></html>"
                        ),
                        content_type="text/html",
                        status_code=200,
                    ),
                )
            ]

        def fake_parse_research_sources(db, *, task, discovery, fetched_sources, settings, write_event):
            source = models.Source(
                task_id=task.id,
                url="https://cursor.example/pricing",
                canonical_url="https://cursor.example/pricing",
                source_type="official",
                title="Cursor Pricing",
                publisher="cursor.example",
                content_hash="cursor-hash",
                is_primary=True,
            )
            db.add(source)
            db.flush()
            parsed_page = html_parser.parse_html(
                "<html><head><title>Cursor Pricing</title></head><body>"
                "<p>Cursor workflow controls and pricing details are documented for enterprise teams with admin support, "
                "including repository policy controls, shared workspace administration, audit logging, and procurement review. "
                "</p></body></html>"
            )
            return [
                collection.ParsedSource(
                    result=fetched_sources[0].result,
                    fetched=fetched_sources[0].fetched,
                    parsed=parsed_page,
                    source_id=source.id,
                )
            ]

        def fail_once_extract_evidence(db, *, task, discovery, parsed_sources, write_event):
            calls["count"] += 1
            if calls["count"] == 1:
                raise ValueError("parsed_sources_missing")
            assert parsed_sources
            return original_extract_evidence(
                db,
                task=task,
                discovery=discovery,
                parsed_sources=parsed_sources,
                write_event=write_event,
            )

        monkeypatch.setattr(research_service, "discover_research_sources", fake_discover_research_sources)
        monkeypatch.setattr(research_service, "fetch_research_sources", fake_fetch_research_sources)
        monkeypatch.setattr(research_service, "parse_research_sources", fake_parse_research_sources)
        monkeypatch.setattr(research_service, "extract_research_evidence", fail_once_extract_evidence)

        with pytest.raises(ValueError, match="parsed_sources_missing"):
            research_graph.run_research_workflow(db, run.id)

        latest_success = (
            db.query(models.WorkflowCheckpoint)
            .filter_by(run_id=run.id, status="succeeded")
            .order_by(models.WorkflowCheckpoint.sequence_no.desc())
            .first()
        )
        assert latest_success is not None
        assert latest_success.node_name == "parse_sources"
        checkpoint_state = research_service.decode_json(latest_success.state_json)
        parsed_state = checkpoint_state["summary"]["parsed_sources_state"]
        assert len(parsed_state) == 1
        assert parsed_state[0]["source_id"]

        resumed = research_graph.run_research_workflow(db, run.id, resume=True)

        assert resumed.status == models.RunStatus.completed.value
        assert resumed.current_stage == "completed"
        assert calls["count"] == 2
    finally:
        db.rollback()
        db.close()


def test_stage_five_workflow_retries_retryable_node_once(monkeypatch):
    from app.workflows import research_graph

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor retry behavior",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        run = research_service.create_run(db, task.id)
        original_fetch_sources = research_service.fetch_research_sources
        calls = {"count": 0}

        def fail_once_fetch_sources(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("temporary fetch failure")
            return original_fetch_sources(*args, **kwargs)

        monkeypatch.setattr(research_service, "fetch_research_sources", fail_once_fetch_sources)

        result = research_graph.run_research_workflow(db, run.id)

        assert result.status == models.RunStatus.waiting_review.value
        assert calls["count"] == 2
        retry_event = db.query(models.ResearchEvent).filter_by(run_id=run.id, type="node.retrying").one()
        assert retry_event.stage == "fetch_sources"
        payload = research_service.decode_json(retry_event.payload_json)
        assert payload["node_name"] == "fetch_sources"
        assert payload["attempt"] == 1
        assert payload["max_attempts"] == 2
        assert payload["error"] == "temporary fetch failure"
        assert db.query(models.ResearchEvent).filter_by(run_id=run.id, type="node.failed").count() == 0
        fetch_checkpoint = db.query(models.WorkflowCheckpoint).filter_by(run_id=run.id, node_name="fetch_sources").one()
        assert fetch_checkpoint.retry_count == 1
        checkpoint_state = research_service.decode_json(fetch_checkpoint.state_json)
        assert checkpoint_state["summary"]["node_retry_counts"]["fetch_sources"] == 1
    finally:
        db.rollback()
        db.close()


def test_stage_five_workflow_does_not_retry_non_retryable_node_error(monkeypatch):
    from app.workflows import research_graph

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor non retryable workflow error",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        run = research_service.create_run(db, task.id)
        calls = {"count": 0}

        def fail_with_state_error(*args, **kwargs):
            calls["count"] += 1
            raise ValueError("source_discovery_missing")

        monkeypatch.setattr(research_service, "fetch_research_sources", fail_with_state_error)

        with pytest.raises(ValueError, match="source_discovery_missing"):
            research_graph.run_research_workflow(db, run.id)

        assert calls["count"] == 1
        assert db.query(models.ResearchEvent).filter_by(run_id=run.id, type="node.retrying").count() == 0
        failed_event = db.query(models.ResearchEvent).filter_by(run_id=run.id, type="node.failed").one()
        assert failed_event.stage == "fetch_sources"
        payload = research_service.decode_json(failed_event.payload_json)
        assert payload["retryable"] is False
    finally:
        db.rollback()
        db.close()


def test_stage_five_workflow_saves_failed_checkpoint_with_error_summary(monkeypatch):
    from app.workflows import research_graph

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor failed checkpoint summary",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        run = research_service.create_run(db, task.id)

        def fail_with_state_error(*args, **kwargs):
            raise ValueError("source_discovery_missing")

        monkeypatch.setattr(research_service, "fetch_research_sources", fail_with_state_error)

        with pytest.raises(ValueError, match="source_discovery_missing"):
            research_graph.run_research_workflow(db, run.id)

        failed_checkpoint = db.query(models.WorkflowCheckpoint).filter_by(run_id=run.id, node_name="fetch_sources", status="failed").one()
        assert failed_checkpoint.resume_node == "fetch_sources"
        assert failed_checkpoint.retry_count == 0
        assert failed_checkpoint.error_summary == "source_discovery_missing"
        output_summary = research_service.decode_json(failed_checkpoint.output_summary_json)
        assert output_summary["retryable"] is False
        state = research_service.decode_json(failed_checkpoint.state_json)
        assert state["current_node"] == "fetch_sources"
        assert state["errors"] == ["source_discovery_missing"]
    finally:
        db.rollback()
        db.close()


def test_stage_five_llm_schema_failure_can_resume_from_checkpoint(monkeypatch):
    from app.workflows import research_graph

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor LLM schema recovery",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        run = research_service.create_run(db, task.id)
        original_extract_claims = research_service.extract_and_store_claims
        calls = {"count": 0}

        def seed_evidence_for_schema_test(*args, **kwargs):
            research_service.seed_demo_research_objects(db, task.id)
            return collection.CollectionSummary(provider="test", evidence_created=3, sources_created=3)

        monkeypatch.setattr(research_service, "extract_research_evidence", seed_evidence_for_schema_test)

        def fail_schema_once(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise ValueError("schema_validation_failed:claims.0.display_text")
            return original_extract_claims(*args, **kwargs)

        monkeypatch.setattr(research_service, "extract_and_store_claims", fail_schema_once)

        with pytest.raises(ValueError, match="schema_validation_failed"):
            research_graph.run_research_workflow(db, run.id)

        failed_run = db.get(models.TaskRun, run.id)
        assert failed_run is not None
        assert failed_run.status == models.RunStatus.failed.value
        assert failed_run.current_stage == "extract_claims"

        failed_checkpoint = db.query(models.WorkflowCheckpoint).filter_by(run_id=run.id, node_name="extract_claims", status="failed").one()
        assert failed_checkpoint.error_summary == "schema_validation_failed:claims.0.display_text"
        assert failed_checkpoint.retry_count == 0

        latest_success = (
            db.query(models.WorkflowCheckpoint)
            .filter_by(run_id=run.id, status="succeeded")
            .order_by(models.WorkflowCheckpoint.sequence_no.desc())
            .first()
        )
        assert latest_success is not None
        assert latest_success.node_name == "extract_evidence"
        assert latest_success.resume_node == "extract_claims"

        result = research_graph.run_research_workflow(db, run.id, resume=True)

        assert result.status == models.RunStatus.waiting_review.value
        assert result.current_stage == "review_gate"
        assert calls["count"] == 2
        assert db.query(models.Report).filter_by(task_id=task.id).count() == 1
    finally:
        db.rollback()
        db.close()


def test_stage_seven_failed_task_can_resume_from_checkpoint_api(monkeypatch):
    from app.workflows import research_graph

    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        db = SessionLocal()
        try:
            task = research_service.create_task(
                db,
                research_service.ResearchTaskCreate(
                    prompt="Research Cursor failed node resume API",
                    competitors=["Cursor"],
                    dimensions=["workflow"],
                ),
            )
            run = research_service.create_run(db, task.id)
            task_id = task.id
            run_id = run.id
            original_extract_claims = research_service.extract_and_store_claims
            calls = {"count": 0}

            def seed_evidence_for_resume_test(*args, **kwargs):
                research_service.seed_demo_research_objects(db, task_id)
                return collection.CollectionSummary(provider="test", evidence_created=3, sources_created=3)

            monkeypatch.setattr(research_service, "extract_research_evidence", seed_evidence_for_resume_test)

            def fail_once_then_succeed(*args, **kwargs):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise ValueError("schema_validation_failed:claims.0.display_text")
                return original_extract_claims(*args, **kwargs)

            monkeypatch.setattr(research_service, "extract_and_store_claims", fail_once_then_succeed)

            with pytest.raises(ValueError, match="schema_validation_failed"):
                research_graph.run_research_workflow(db, run_id)
        finally:
            db.close()

        response = client.post(f"/v1/research-tasks/{task_id}/resume")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == run_id
        assert body["status"] == models.RunStatus.waiting_review.value
        assert body["current_stage"] == "review_gate"
        assert calls["count"] == 2

        detail = client.get(f"/v1/research-tasks/{task_id}").json()
        assert detail["task"]["current_run_id"] == run_id
        assert [item["id"] for item in detail["runs"]] == [run_id]


def test_stage_five_report_generation_final_failure_records_node_failed(monkeypatch):
    from app.workflows import research_graph

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor report failure observability",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        run = research_service.create_run(db, task.id)

        monkeypatch.setattr(
            research_service,
            "extract_research_evidence",
            lambda *args, **kwargs: collection.CollectionSummary(provider="test", evidence_created=1, sources_created=1),
        )
        monkeypatch.setattr(research_service, "extract_and_store_claims", lambda *args, **kwargs: claim_extractor.ClaimExtractionResult(claims=[]))

        def always_fail_report(*args, **kwargs):
            raise RuntimeError("permanent report renderer failure")

        monkeypatch.setattr(research_service, "create_claim_report", always_fail_report)

        with pytest.raises(RuntimeError, match="report_generation_failed"):
            research_graph.run_research_workflow(db, run.id)

        report_failures = db.query(models.ResearchEvent).filter_by(run_id=run.id, type="report.generate_failed").all()
        assert len(report_failures) == research_service.REPORT_MAX_ATTEMPTS
        node_failed = db.query(models.ResearchEvent).filter_by(run_id=run.id, type="node.failed").one()
        assert node_failed.stage == "generate_report"
        payload = research_service.decode_json(node_failed.payload_json)
        assert payload["node_name"] == "generate_report"
        assert payload["retryable"] is False
        assert "report_generation_failed" in payload["error"]
        assert db.query(models.ResearchEvent).filter_by(run_id=run.id, type="node.retrying", stage="generate_report").count() == 0
    finally:
        db.rollback()
        db.close()


def test_stage_seven_report_sections_include_citation_evidence():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        created = client.post(
            "/v1/research-tasks",
            json={
                "title": "Stage 7.6B section citation evidence",
                "prompt": "Research Trae, Cursor, GitHub Copilot, and Windsurf section evidence display",
                "competitors": ["Trae", "Cursor", "Windsurf"],
                "dimensions": ["pricing", "enterprise controls"],
            },
        )
        assert created.status_code == 201
        task_id = created.json()["id"]

        confirmed = client.post(f"/v1/research-tasks/{task_id}/confirm")
        assert confirmed.status_code == 200

        detail = client.get(f"/v1/research-tasks/{task_id}")

        assert detail.status_code == 200
        body = detail.json()
        evidence_ids = {item["id"] for item in body["evidence"]}
        report = body["reports"][0]
        assert report["sections"]
        assert all("evidence" in section for section in report["sections"])

        evidence_sections = [section for section in report["sections"] if section["evidence"]]
        assert {section["section_type"] for section in evidence_sections} >= {"executive_summary", "comparison"}
        first_evidence = evidence_sections[0]["evidence"][0]
        assert first_evidence["id"] in evidence_ids
        assert first_evidence["quote"]
        assert first_evidence["source_title"]
        assert first_evidence["source_url"].startswith("https://")
        assert 0 <= first_evidence["quality_score"] <= 1
        assert first_evidence["claim_ids"]


def test_stage_seven_report_regeneration_blocks_unresolved_risky_claims():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        created = client.post(
            "/v1/research-tasks",
            json={
                "title": "Stage 7.6A unresolved report regeneration",
                "prompt": "Research Trae, Cursor, GitHub Copilot, and Windsurf report regeneration",
                "competitors": ["Trae", "Cursor", "Windsurf"],
                "dimensions": ["pricing", "risk"],
            },
        )
        assert created.status_code == 201
        task_id = created.json()["id"]

        run = client.post(f"/v1/research-tasks/{task_id}/confirm")
        assert run.status_code == 200
        detail = client.get(f"/v1/research-tasks/{task_id}").json()
        assert [report["version"] for report in detail["reports"]] == [1]
        assert any(
            claim["status"] in {"conflict", "undisclosed", "low_confidence", "needs_evidence"}
            for claim in detail["claims"]
        )

        response = client.post(f"/v1/research-tasks/{task_id}/reports/regenerate")

        assert response.status_code == 409
        assert "unresolved" in response.text


def test_stage_seven_report_regeneration_creates_manual_next_version():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        created = client.post(
            "/v1/research-tasks",
            json={
                "title": "Stage 7.6A manual report regeneration",
                "prompt": "Research Trae, Cursor, GitHub Copilot, and Windsurf report regeneration",
                "competitors": ["Trae", "Cursor", "Windsurf"],
                "dimensions": ["pricing", "risk"],
            },
        )
        assert created.status_code == 201
        task_id = created.json()["id"]

        run = client.post(f"/v1/research-tasks/{task_id}/confirm")
        assert run.status_code == 200
        detail = client.get(f"/v1/research-tasks/{task_id}").json()
        risky_claims = [
            claim
            for claim in detail["claims"]
            if claim["status"] in {"conflict", "undisclosed", "low_confidence", "needs_evidence"}
        ]
        assert risky_claims

        for claim in risky_claims:
            decision = "exclude" if claim["status"] == "conflict" else "accept"
            reviewed = client.post(
                f"/v1/claims/{claim['id']}/review",
                json={"decision": decision, "reason": "manual review resolved"},
            )
            assert reviewed.status_code == 201

        completed = client.get(f"/v1/research-tasks/{task_id}").json()
        assert completed["task"]["status"] == "completed"
        assert [report["version"] for report in completed["reports"]] == [1, 2]

        response = client.post(f"/v1/research-tasks/{task_id}/reports/regenerate")

        assert response.status_code == 201
        report = response.json()
        assert report["version"] == 3
        assert report["input_snapshot"]["report_generation"]["reason"] == "manual_regenerate"

        refreshed = client.get(f"/v1/research-tasks/{task_id}").json()
        assert [report["version"] for report in refreshed["reports"]] == [1, 2, 3]


def test_stage_seven_competitor_profiles_persist_sources_and_aggregate_stats():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        created_task = client.post(
            "/v1/research-tasks",
            json={
                "title": "Stage 7.7A competitor profile stats",
                "prompt": "Research Cursor, Trae, and Windsurf competitor library stats",
                "competitors": ["Cursor", "Trae", "Windsurf"],
                "dimensions": ["pricing", "enterprise controls"],
            },
        )
        assert created_task.status_code == 201
        task_id = created_task.json()["id"]
        confirmed = client.post(f"/v1/research-tasks/{task_id}/confirm")
        assert confirmed.status_code == 200

        created_profile = client.post(
            "/v1/competitors",
            json={
                "name": "Cursor",
                "category": "AI code editor",
                "description": "Agentic code editor for teams",
                "homepage_url": "https://cursor.com",
                "source_urls": [
                    {"label": "Pricing", "url": "https://cursor.com/pricing", "source_type": "official"},
                    {"label": "Docs", "url": "https://docs.cursor.com", "source_type": "docs"},
                ],
            },
        )

        assert created_profile.status_code == 201
        profile = created_profile.json()
        assert profile["name"] == "Cursor"
        assert profile["workspace_id"] == "default"
        assert profile["source_urls"][0]["label"] == "Pricing"
        assert profile["source_urls"][0]["url"] == "https://cursor.com/pricing"
        assert profile["task_count"] == 1
        assert profile["verified_claim_count"] >= 1
        assert profile["risky_claim_count"] == 0
        assert profile["report_count"] == 1

        duplicate = client.post(
            "/v1/competitors",
            json={"name": "Cursor", "category": "Duplicate", "source_urls": []},
        )
        assert duplicate.status_code == 409

        listed = client.get("/v1/competitors")

        assert listed.status_code == 200
        rows = listed.json()
        assert [row["name"] for row in rows] == ["Cursor"]
        assert rows[0]["source_count"] == 2
        assert rows[0]["task_count"] == 1
        assert rows[0]["report_count"] == 1


def test_stage_seven_task_creation_reuses_competitor_profile_sources():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        profile_response = client.post(
            "/v1/competitors",
            json={
                "name": "Cursor",
                "category": "AI code editor",
                "homepage_url": "https://cursor.com",
                "source_urls": [
                    {"label": "Pricing", "url": "https://cursor.com/pricing", "source_type": "official"},
                    {"label": "Docs", "url": "https://docs.cursor.com", "source_type": "docs"},
                ],
            },
        )
        assert profile_response.status_code == 201
        profile = profile_response.json()

        created = client.post(
            "/v1/research-tasks",
            json={
                "title": "Stage 7.7B profile source reuse",
                "prompt": "Research Cursor and Trae source reuse from competitor library",
                "competitors": ["Cursor", "Trae"],
                "dimensions": ["pricing", "enterprise controls"],
                "source_preferences": ["https://example.com/manual-source", "https://cursor.com/pricing"],
            },
        )

        assert created.status_code == 201
        scope = created.json()["scope"]
        assert scope["source_preferences"] == [
            "https://example.com/manual-source",
            "https://cursor.com/pricing",
            "https://docs.cursor.com",
        ]
        assert scope["competitor_profile_reuse"] == [
            {
                "profile_id": profile["id"],
                "name": "Cursor",
                "source_count": 2,
                "source_urls": [
                    {"label": "Pricing", "url": "https://cursor.com/pricing", "source_type": "official"},
                    {"label": "Docs", "url": "https://docs.cursor.com", "source_type": "docs"},
                ],
            }
        ]


def test_stage_seven_research_tasks_are_filtered_by_workspace_and_user():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        alpha = client.post(
            "/v1/research-tasks",
            json={
                "title": "Alpha workspace task",
                "prompt": "Research Cursor in alpha workspace",
                "competitors": ["Cursor"],
                "dimensions": ["pricing", "enterprise controls"],
                "workspace_id": "workspace-alpha",
                "created_by": "alice",
            },
        )
        beta = client.post(
            "/v1/research-tasks",
            json={
                "title": "Beta workspace task",
                "prompt": "Research Cursor in beta workspace",
                "competitors": ["Cursor"],
                "dimensions": ["pricing", "enterprise controls"],
                "workspace_id": "workspace-beta",
                "created_by": "bob",
            },
        )

        assert alpha.status_code == 201
        assert beta.status_code == 201
        assert alpha.json()["workspace_id"] == "workspace-alpha"
        assert beta.json()["workspace_id"] == "workspace-beta"

        alpha_list = client.get("/v1/research-tasks?workspace_id=workspace-alpha")
        alice_list = client.get("/v1/research-tasks?created_by=alice")
        beta_alice_list = client.get("/v1/research-tasks?workspace_id=workspace-beta&created_by=alice")

        assert alpha_list.status_code == 200
        assert [task["id"] for task in alpha_list.json()] == [alpha.json()["id"]]
        assert [task["id"] for task in alice_list.json()] == [alpha.json()["id"]]
        assert beta_alice_list.status_code == 200
        assert beta_alice_list.json() == []


def test_stage_seven_workspace_headers_block_cross_workspace_task_detail():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        created = client.post(
            "/v1/research-tasks",
            json={
                "title": "Alpha workspace task",
                "prompt": "Research Cursor in alpha workspace",
                "competitors": ["Cursor"],
                "dimensions": ["pricing", "enterprise controls"],
                "workspace_id": "workspace-alpha",
                "created_by": "alice",
            },
        )

        assert created.status_code == 201
        task_id = created.json()["id"]

        visible = client.get(
            f"/v1/research-tasks/{task_id}",
            headers={"X-Workspace-Id": "workspace-alpha", "X-User-Id": "alice"},
        )
        hidden = client.get(
            f"/v1/research-tasks/{task_id}",
            headers={"X-Workspace-Id": "workspace-beta", "X-User-Id": "bob"},
        )

        assert visible.status_code == 200
        assert hidden.status_code == 404


def test_stage_six_celery_confirm_enqueues_workflow_task_with_priority(monkeypatch):
    from app.config import get_settings
    from app.workers import tasks as worker_tasks

    monkeypatch.setenv("TASK_MODE", "celery")
    get_settings.cache_clear()
    captured: dict[str, object] = {}

    def fail_delay(*args, **kwargs):
        raise AssertionError("celery mode should enqueue with apply_async so priority can be passed")

    def capture_apply_async(*, args=None, kwargs=None, priority=None, queue=None):
        captured["args"] = args
        captured["kwargs"] = kwargs
        captured["priority"] = priority
        captured["queue"] = queue

        class FakeAsyncResult:
            id = "celery-test-id"

        return FakeAsyncResult()

    monkeypatch.setattr(worker_tasks.run_research_task, "delay", fail_delay)
    monkeypatch.setattr(worker_tasks.run_research_task, "apply_async", capture_apply_async)

    try:
        with TestClient(app) as client:
            client.delete("/v1/dev/demo-data")
            created = client.post(
                "/v1/research-tasks",
                json={
                    "title": "Celery priority enqueue",
                    "prompt": "Research Cursor Celery workflow enqueue behavior",
                    "competitors": ["Cursor"],
                    "dimensions": ["workflow", "async"],
                },
            )
            assert created.status_code == 201

            confirmed = client.post(f"/v1/research-tasks/{created.json()['id']}/confirm?priority=3")

            assert confirmed.status_code == 200
            body = confirmed.json()
            assert body["status"] == models.RunStatus.queued.value
            assert body["current_stage"] == "queued"
            assert body["priority"] == 3
            assert captured["args"] == [body["id"]]
            assert captured["priority"] == 3
            assert captured["queue"] == "research"
    finally:
        monkeypatch.delenv("TASK_MODE", raising=False)
        get_settings.cache_clear()


def test_stage_six_celery_worker_auto_resumes_from_checkpoint(monkeypatch):
    from app.workers import tasks as worker_tasks

    captured: dict[str, object] = {}

    class FakeDB:
        def close(self) -> None:
            return None

    def fake_session_local():
        return FakeDB()

    def fake_checkpoint(db, run_id):
        captured["checkpoint_run_id"] = run_id
        return object()

    def fake_run_workflow(db, run_id, delay_seconds=0.2, resume=False):
        captured["run_id"] = run_id
        captured["resume"] = resume

    monkeypatch.setattr(worker_tasks, "SessionLocal", fake_session_local)
    monkeypatch.setattr(worker_tasks, "latest_success_checkpoint", fake_checkpoint)
    monkeypatch.setattr(worker_tasks, "run_research_workflow", fake_run_workflow)

    result = worker_tasks.run_research_task.run("run-auto-resume")

    assert result == "run-auto-resume"
    assert captured["checkpoint_run_id"] == "run-auto-resume"
    assert captured["run_id"] == "run-auto-resume"
    assert captured["resume"] is True


def test_inline_confirm_can_launch_workflow_in_background(monkeypatch):
    from app.api import routes

    captured: dict[str, object] = {}

    def capture_background_run(run_id: str, resume: bool = False) -> None:
        captured["run_id"] = run_id
        captured["resume"] = resume

    monkeypatch.setattr(routes, "run_workflow_in_background", capture_background_run)

    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        created = client.post(
            "/v1/research-tasks",
            json={
                "title": "Background mainline",
                "prompt": "Research Cursor background workflow launch behavior",
                "competitors": ["Cursor"],
                "dimensions": ["workflow", "events"],
            },
        )
        assert created.status_code == 201

        confirmed = client.post(f"/v1/research-tasks/{created.json()['id']}/confirm?background=true&priority=4")

        assert confirmed.status_code == 200
        body = confirmed.json()
        assert body["status"] == models.RunStatus.queued.value
        assert body["current_stage"] == "queued"
        assert body["priority"] == 4
        assert captured == {"run_id": body["id"], "resume": False}

        detail = client.get(f"/v1/research-tasks/{created.json()['id']}").json()
        assert detail["task"]["status"] == models.TaskStatus.queued.value
        assert detail["task"]["current_run_id"] == body["id"]


def test_rerun_and_resume_can_launch_workflow_in_background(monkeypatch):
    from app.api import routes

    captured: list[dict[str, object]] = []

    def capture_background_run(run_id: str, resume: bool = False) -> None:
        captured.append({"run_id": run_id, "resume": resume})

    monkeypatch.setattr(routes, "run_workflow_in_background", capture_background_run)

    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        created = client.post(
            "/v1/research-tasks",
            json={
                "title": "Background rerun",
                "prompt": "Research Cursor background rerun behavior",
                "competitors": ["Cursor"],
                "dimensions": ["workflow", "retry"],
            },
        )
        assert created.status_code == 201
        task_id = created.json()["id"]

        first_run = client.post(f"/v1/research-tasks/{task_id}/confirm")
        assert first_run.status_code == 200

        rerun = client.post(f"/v1/research-tasks/{task_id}/runs?background=true&priority=2")
        assert rerun.status_code == 201
        rerun_body = rerun.json()
        assert rerun_body["status"] == models.RunStatus.queued.value
        assert rerun_body["priority"] == 2
        assert captured[-1] == {"run_id": rerun_body["id"], "resume": False}

        db = SessionLocal()
        try:
            resume_task = research_service.create_task(
                db,
                research_service.ResearchTaskCreate(
                    title="Background resume",
                    prompt="Research Cursor background resume behavior",
                    competitors=["Cursor"],
                    dimensions=["workflow", "resume"],
                ),
            )
            failed_run = research_service.create_run(db, resume_task.id)
            resume_task.status = models.TaskStatus.failed.value
            failed_run.status = models.RunStatus.failed.value
            failed_run.current_stage = "fetch_sources"
            failed_run.error_message = "temporary fetch failure"
            failed_run.finished_at = models.utc_now()
            db.add(
                models.WorkflowCheckpoint(
                    run_id=failed_run.id,
                    sequence_no=1,
                    node_name="plan_research",
                    resume_node="discover_sources",
                    status="succeeded",
                    input_summary_json="{}",
                    output_summary_json="{}",
                    state_json=research_service.encode_json(
                        {
                            "task_id": resume_task.id,
                            "run_id": failed_run.id,
                            "scope": research_service.decode_json(failed_run.input_snapshot_json),
                            "summary": {},
                            "errors": [],
                            "current_node": "discover_sources",
                        }
                    ),
                )
            )
            db.commit()
            resume_task_id = resume_task.id
            failed_run_id = failed_run.id
        finally:
            db.close()

        resumed = client.post(f"/v1/research-tasks/{resume_task_id}/resume?background=true")
        assert resumed.status_code == 200
        resumed_body = resumed.json()
        assert resumed_body["id"] == failed_run_id
        assert resumed_body["status"] == models.RunStatus.queued.value
        assert resumed_body["current_stage"] == "discover_sources"
        assert captured[-1] == {"run_id": failed_run_id, "resume": True}


def test_stage_five_resume_uses_latest_success_checkpoint(monkeypatch):
    from app.api import routes
    from app.workflows import research_graph

    captured: dict[str, object] = {}

    def capture_background_run(run_id: str, resume: bool = False) -> None:
        captured["run_id"] = run_id
        captured["resume"] = resume

    def fail_verify_claims(*args, **kwargs):
        raise RuntimeError("claim verification exploded")

    monkeypatch.setattr(routes, "run_workflow_in_background", capture_background_run)
    monkeypatch.setattr(research_service, "verify_claims", fail_verify_claims)

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                title="Checkpoint resume",
                prompt="Research Cursor checkpoint resume behavior",
                competitors=["Cursor"],
                dimensions=["workflow", "checkpoint"],
            ),
        )
        run = research_service.create_run(db, task.id)

        with pytest.raises(RuntimeError, match="claim verification exploded"):
            research_graph.run_research_workflow(db, run.id)

        checkpoint = research_graph.latest_success_checkpoint(db, run.id)
        assert checkpoint is not None
        assert checkpoint.node_name == "extract_claims"
        assert checkpoint.resume_node == "verify_claims"
        assert checkpoint.status == "succeeded"

        task_id = task.id
        run_id = run.id
    finally:
        db.close()

    with TestClient(app) as client:
        resumed = client.post(f"/v1/research-tasks/{task_id}/resume?background=true")

    assert resumed.status_code == 200
    body = resumed.json()
    assert body["id"] == run_id
    assert body["status"] == models.RunStatus.queued.value
    assert body["current_stage"] == "verify_claims"
    assert captured == {"run_id": run_id, "resume": True}


def test_stage_five_resume_does_not_duplicate_existing_report_side_effect(monkeypatch):
    from app.workflows import research_graph

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                title="Checkpoint report idempotency",
                prompt="Research Cursor checkpoint report idempotency",
                competitors=["Cursor"],
                dimensions=["workflow", "report"],
            ),
        )
        run = research_service.create_run(db, task.id)
        original_save_success_checkpoint = research_graph.save_success_checkpoint
        fail_once = {"pending": True}

        def fail_after_report_side_effect(*args, **kwargs):
            if kwargs.get("node_name") == "generate_report" and fail_once["pending"]:
                fail_once["pending"] = False
                raise RuntimeError("checkpoint write failed after report")
            return original_save_success_checkpoint(*args, **kwargs)

        monkeypatch.setattr(research_graph, "save_success_checkpoint", fail_after_report_side_effect)

        with pytest.raises(RuntimeError, match="checkpoint write failed after report"):
            research_graph.run_research_workflow(db, run.id)

        source_count = db.query(models.Source).filter_by(task_id=task.id).count()
        evidence_count = db.query(models.Evidence).join(models.Source).filter(models.Source.task_id == task.id).count()
        claim_count = db.query(models.Claim).filter_by(task_id=task.id).count()
        assert db.query(models.Report).filter_by(task_id=task.id).count() == 1
        assert db.query(models.ResearchEvent).filter_by(run_id=run.id, type="report.created").count() == 1

        task.status = models.TaskStatus.failed.value
        run.status = models.RunStatus.failed.value
        run.current_stage = "generate_report"
        run.error_message = "checkpoint write failed after report"
        run.finished_at = models.utc_now()
        db.commit()

        resumed = research_graph.run_research_workflow(db, run.id, resume=True)

        assert resumed.status in {models.RunStatus.waiting_review.value, models.RunStatus.completed.value}
        assert db.query(models.Source).filter_by(task_id=task.id).count() == source_count
        assert db.query(models.Evidence).join(models.Source).filter(models.Source.task_id == task.id).count() == evidence_count
        assert db.query(models.Claim).filter_by(task_id=task.id).count() == claim_count
        assert db.query(models.Report).filter_by(task_id=task.id).count() == 1
        assert db.query(models.ResearchEvent).filter_by(run_id=run.id, type="report.created").count() == 1
    finally:
        db.rollback()
        db.close()


def test_stage_six_worker_health_reports_celery_configuration(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("TASK_MODE", "celery")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    get_settings.cache_clear()

    try:
        with TestClient(app) as client:
            response = client.get("/v1/worker/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "configured"
        assert body["task_mode"] == "celery"
        assert body["broker"] == "redis://localhost:6379/0"
        assert body["result_backend"] == "redis://localhost:6379/1"
        assert body["registered_task"] == "research.run"
    finally:
        monkeypatch.delenv("TASK_MODE", raising=False)
        monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
        monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)
        get_settings.cache_clear()


def test_stage_six_metrics_endpoint_reports_runtime_counts():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        created = client.post(
            "/v1/research-tasks",
            json={
                "title": "Metrics endpoint smoke test",
                "prompt": "Research Cursor metrics endpoint smoke test",
                "competitors": ["Cursor"],
                "dimensions": ["workflow"],
            },
        )
        assert created.status_code == 201

        response = client.get("/v1/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["environment"] == "dev"
    assert body["task_mode"] == "inline"
    assert body["database_backend"] == "sqlite"
    assert body["counts"]["research_tasks"] == 1
    assert body["counts"]["task_runs"] == 0
    assert body["counts"]["reports"] == 0


def test_cancel_research_task_api_cancels_queued_run():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        db = SessionLocal()
        try:
            task = research_service.create_task(
                db,
                research_service.ResearchTaskCreate(
                    prompt="Research Cursor cancellation API",
                    competitors=["Cursor"],
                    dimensions=["workflow"],
                ),
            )
            run = research_service.create_run(db, task.id)
        finally:
            db.close()

        response = client.post(f"/v1/research-tasks/{task.id}/cancel", json={"reason": "user changed scope"})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == models.RunStatus.canceled.value
        assert body["current_stage"] == "canceled"
        assert body["error_message"] == "user changed scope"

        detail = client.get(f"/v1/research-tasks/{task.id}").json()
        assert detail["task"]["status"] == models.TaskStatus.canceled.value
        assert detail["task"]["failure_reason"] == "user changed scope"

        events = client.get(f"/v1/research-tasks/{task.id}/events").json()
        assert events[-1]["type"] == "run.canceled"
        assert events[-1]["stage"] == "canceled"


def test_task_events_follow_current_queued_run_instead_of_historical_run():
    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        created = client.post(
            "/v1/research-tasks",
            json={
                "title": "Queued rerun event selection",
                "prompt": "Research Cursor queued rerun event selection behavior",
                "competitors": ["Cursor"],
                "dimensions": ["workflow", "events"],
            },
        )
        assert created.status_code == 201
        task_id = created.json()["id"]

        first_run = client.post(f"/v1/research-tasks/{task_id}/confirm")
        assert first_run.status_code == 200
        assert client.get(f"/v1/research-tasks/{task_id}/events").json()

        db = SessionLocal()
        try:
            queued_rerun = research_service.create_run(db, task_id, allow_rerun=True)
            assert queued_rerun.status == models.RunStatus.queued.value
            assert queued_rerun.started_at is None
        finally:
            db.close()

        detail = client.get(f"/v1/research-tasks/{task_id}").json()
        assert detail["task"]["current_run_id"] == queued_rerun.id

        current_events = client.get(f"/v1/research-tasks/{task_id}/events")
        assert current_events.status_code == 200
        assert current_events.json() == []


def test_stage_five_workflow_stops_when_task_is_canceled_before_start():
    from app.workflows import research_graph

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor canceled before workflow",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        run = research_service.create_run(db, task.id)
        transition_reason = "canceled before worker picked up run"
        research_service.cancel_research_task(db, task.id, reason=transition_reason)

        result = research_graph.run_research_workflow(db, run.id)

        assert result.status == models.RunStatus.canceled.value
        assert result.current_stage == "canceled"
        skipped_event = db.query(models.ResearchEvent).filter_by(run_id=run.id, type="node.skipped").one()
        assert skipped_event.stage == "initialize_run"
        payload = research_service.decode_json(skipped_event.payload_json)
        assert payload["node_name"] == "initialize_run"
        assert payload["reason"] == "task_canceled"
        assert db.query(models.Report).filter_by(task_id=task.id).count() == 0
    finally:
        db.rollback()
        db.close()


def test_stage_five_verify_claims_is_independent_failure_boundary(monkeypatch):
    from app.workflows import research_graph

    db = SessionLocal()
    try:
        task = research_service.create_task(
            db,
            research_service.ResearchTaskCreate(
                prompt="Research Cursor claim verification observability",
                competitors=["Cursor"],
                dimensions=["workflow"],
            ),
        )
        run = research_service.create_run(db, task.id)

        def fail_verify_claims(*args, **kwargs):
            raise RuntimeError("claim verification exploded")

        monkeypatch.setattr(research_service, "verify_claims", fail_verify_claims, raising=False)

        with pytest.raises(RuntimeError, match="claim verification exploded"):
            research_graph.run_research_workflow(db, run.id)

        failed_event = db.query(models.ResearchEvent).filter_by(run_id=run.id, type="node.failed").one()
        assert failed_event.stage == "verify_claims"
        assert failed_event.severity == "error"
        payload = research_service.decode_json(failed_event.payload_json)
        assert payload["stage"] == "verify_claims"
        assert payload["node_name"] == "verify_claims"
        assert payload["duration_ms"] >= 0
        assert payload["input_summary"]["run_id"] == run.id
        assert payload["output_summary"] == {}
        assert payload["error"] == "claim verification exploded"
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
            Settings(search_provider="tavily", artifact_storage_dir=str(tmp_path)),
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
            settings=Settings(search_provider="tavily", artifact_storage_dir=str(tmp_path)),
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
    assert llm.build_llm_extractor(Settings(search_provider="test")) is None


def test_stage_four_build_llm_extractor_enables_openai_compatible_with_api_key():
    extractor = llm.build_llm_extractor(
        Settings(search_provider="test", llm_api_key="test-key", llm_provider="openai_compatible")
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


MANUAL_URL_FLOW_HTML = """
<html>
  <head><title>Cursor Pricing</title></head>
  <body>
    <article>
      <p>Cursor pricing and plans for teams and enterprises. The Pro plan is priced at 20 dollars per month per seat, while the Business plan is priced at 40 dollars per seat with centralized billing and admin controls.</p>
      <p>Enterprise buyers comparing AI coding assistants should review the pricing page details, including seat based subscription billing, privacy mode support, and organization level management controls for governance.</p>
      <p>The pricing page also documents team management features, enterprise readiness controls, and workflow integration options that organizations evaluate when choosing between AI coding assistant vendors.</p>
      <p>Additional pricing notes explain how plan limits apply, how billing works for annual subscriptions, and how admin controls help enterprises manage seats and compliance requirements across engineering teams.</p>
    </article>
  </body>
</html>
"""


def test_stage_eight_manual_url_flow_without_tavily_key(monkeypatch, tmp_path):
    """8.3 端到端验收：无 Tavily API Key 时，手动 URL 仍可走完采集、证据、Claim、报告全链路。"""
    monkeypatch.setenv("ARTIFACT_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()

    class FakeFetcher:
        def __init__(self, **kwargs) -> None:
            pass

        def fetch(self, url: str) -> FetchResult:
            return FetchResult(
                url=url,
                final_url=url,
                content_type="text/html; charset=utf-8",
                status_code=200,
                html=MANUAL_URL_FLOW_HTML,
            )

    monkeypatch.setattr(collection, "HttpPageFetcher", FakeFetcher)

    try:
        with TestClient(app) as client:
            client.delete("/v1/dev/demo-data")
            created = client.post(
                "/v1/research-tasks",
                json={
                    "prompt": "调研 Cursor 的定价策略和企业能力",
                    "competitors": ["Cursor"],
                    "dimensions": ["定价策略"],
                    "source_preferences": ["https://manual.example/pricing"],
                },
            )
            assert created.status_code == 201
            task_id = created.json()["id"]

            confirmed = client.post(f"/v1/research-tasks/{task_id}/confirm")
            assert confirmed.status_code == 200
            # 高质量手动来源产出的 Claim 无风险时，review gate 直接放行
            assert confirmed.json()["status"] in {"waiting_review", "completed"}

            detail = client.get(f"/v1/research-tasks/{task_id}").json()
            assert len(detail["sources"]) == 1
            assert detail["sources"][0]["url"] == "https://manual.example/pricing"
            assert detail["sources"][0]["canonical_url"] == "https://manual.example/pricing"
            assert detail["evidence"], "手动 URL 流程应从抓取页面产出 Evidence"
            assert detail["claims"], "手动 URL 流程应产出 Claim"
            assert len(detail["reports"]) == 1

            events = client.get(f"/v1/research-tasks/{task_id}/events").json()
            event_types = [event["type"] for event in events]
            assert "search.started" in event_types
            assert "source.found" in event_types
            assert "evidence.created" in event_types
    finally:
        get_settings.cache_clear()


def test_stage_eight_rule_based_fallback_flow_without_llm_key(monkeypatch, tmp_path):
    """8.3 端到端验收：无 LLM API Key 时，规则抽取仍产出绑定 Evidence 的 Claim，并支持导出。"""
    monkeypatch.setenv("ARTIFACT_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    assert llm.build_llm_extractor(get_settings()) is None

    class FakeFetcher:
        def __init__(self, **kwargs) -> None:
            pass

        def fetch(self, url: str) -> FetchResult:
            return FetchResult(
                url=url,
                final_url=url,
                content_type="text/html; charset=utf-8",
                status_code=200,
                html=MANUAL_URL_FLOW_HTML,
            )

    monkeypatch.setattr(collection, "HttpPageFetcher", FakeFetcher)

    try:
        with TestClient(app) as client:
            client.delete("/v1/dev/demo-data")
            created = client.post(
                "/v1/research-tasks",
                json={
                    "prompt": "调研 Cursor 的定价策略",
                    "competitors": ["Cursor"],
                    "dimensions": ["定价策略"],
                    "source_preferences": ["https://manual.example/pricing"],
                },
            )
            assert created.status_code == 201
            task_id = created.json()["id"]

            confirmed = client.post(f"/v1/research-tasks/{task_id}/confirm")
            assert confirmed.status_code == 200

            detail = client.get(f"/v1/research-tasks/{task_id}").json()
            claims = detail["claims"]
            assert claims, "规则 fallback 应产出 Claim"
            for claim in claims:
                assert claim["evidence_ids"], "规则抽取的 Claim 必须绑定 Evidence"
                assert claim["display_text"].strip()
                assert claim["confidence"] in {"high", "medium"}
                assert claim["claim_type"] == "pricing"
            evidence_ids = {evidence["id"] for evidence in detail["evidence"]}
            assert all(evidence_id in evidence_ids for claim in claims for evidence_id in claim["evidence_ids"])

            report = detail["reports"][0]
            assert report["citation_coverage"] > 0

            markdown_export = client.post(f"/v1/reports/{report['id']}/export?format=markdown")
            assert markdown_export.status_code == 200
            assert markdown_export.headers["x-artifact-object-key"].startswith(f"reports/{task_id}/")
            assert "Cursor" in markdown_export.json()["content"]
    finally:
        get_settings.cache_clear()
