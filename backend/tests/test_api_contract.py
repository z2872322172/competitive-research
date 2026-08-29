import hashlib

import pytest
from fastapi.testclient import TestClient

from app import models
from app.config import Settings, get_settings
from app.db import SessionLocal, init_db
from app.main import app
from app.services import collection, research_service
from app.services.analysis import claim_extractor
from app.services.fetching.fetcher import FetchResult
from app.services.search import indexing as search_indexing
from app.services.search.base import SearchResult


@pytest.fixture(autouse=True)
def disable_real_search(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "")
    get_settings.cache_clear()
    init_db()
    yield
    get_settings.cache_clear()


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
        missing_source = client.get("/v1/sources/999999/snapshot")

        assert response.status_code == 200
        body = response.json()
        assert body["source_id"] == source_id
        assert body["artifact_type"] == "html_snapshot"
        assert body["available"] is False
        assert body["summary"] == ""
        assert body["char_count"] == 0
        assert missing_source.status_code == 404

def test_stage_six_demo_sources_persist_snapshots_in_artifact_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTIFACT_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        task = client.post(
            "/v1/research-tasks",
            json={
                "prompt": "Analyze Cursor pricing and enterprise controls",
                "competitors": ["Cursor"],
                "dimensions": ["pricing"],
            },
        ).json()
        client.post(f"/v1/research-tasks/{task['id']}/confirm")

        detail = client.get(f"/v1/research-tasks/{task['id']}").json()
        assert detail["sources"]
        for source in detail["sources"]:
            snapshot = client.get(f"/v1/sources/{source['id']}/snapshot").json()
            assert snapshot["available"] is True
            assert snapshot["object_key"].startswith(f"snapshots/{task['id']}/")
            assert snapshot["char_count"] > 0
            assert snapshot["summary"]

        snapshot_dir = tmp_path / "snapshots" / str(task["id"])
        assert snapshot_dir.exists()
        assert list(snapshot_dir.glob("*.html"))

    get_settings.cache_clear()

def test_stage_six_source_snapshot_raw_returns_file_bytes(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTIFACT_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        task = client.post(
            "/v1/research-tasks",
            json={
                "prompt": "Analyze Cursor pricing and enterprise controls",
                "competitors": ["Cursor"],
                "dimensions": ["pricing"],
            },
        ).json()
        client.post(f"/v1/research-tasks/{task['id']}/confirm")

        detail = client.get(f"/v1/research-tasks/{task['id']}").json()
        source = detail["sources"][0]
        response = client.get(f"/v1/sources/{source['id']}/snapshot/raw")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        object_key = response.headers["x-artifact-object-key"]
        assert object_key == f"snapshots/{task['id']}/{source['id']}.html"
        body = response.content
        assert body.startswith(b"<!doctype html>")
        assert source["title"].encode("utf-8") in body
        assert response.headers["x-artifact-size"] == str(len(body))
        assert hashlib.sha256(body).hexdigest() == response.headers["x-artifact-sha256"]

        stored_file = tmp_path / "snapshots" / str(task["id"]) / f"{source['id']}.html"
        assert stored_file.read_bytes() == body

    get_settings.cache_clear()

def test_stage_six_source_snapshot_raw_error_semantics(monkeypatch, tmp_path):
    monkeypatch.setenv("ARTIFACT_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()

    with TestClient(app) as client:
        client.delete("/v1/dev/demo-data")
        db = SessionLocal()
        try:
            task = models.ResearchTask(title="Raw snapshot errors", prompt="Research raw snapshot errors")
            db.add(task)
            db.flush()

            source_without_artifact = models.Source(
                task_id=task.id,
                url="https://example.com/no-artifact",
                canonical_url="https://example.com/no-artifact",
                source_type="docs",
                title="No Artifact",
                publisher="Example",
                content_hash="noart123",
            )
            db.add(source_without_artifact)
            db.flush()

            source_missing_file = models.Source(
                task_id=task.id,
                url="https://example.com/missing-file",
                canonical_url="https://example.com/missing-file",
                source_type="docs",
                title="Missing File",
                publisher="Example",
                content_hash="miss123",
            )
            db.add(source_missing_file)
            db.flush()
            db.add(
                models.SourceArtifact(
                    source_id=source_missing_file.id,
                    artifact_type="html_snapshot",
                    object_key=f"snapshots/{task.id}/{source_missing_file.id}.html",
                    sha256="miss123",
                )
            )
            db.commit()
            no_artifact_id = source_without_artifact.id
            missing_file_id = source_missing_file.id
        finally:
            db.close()

        unknown = client.get("/v1/sources/999999/snapshot/raw")
        no_artifact = client.get(f"/v1/sources/{no_artifact_id}/snapshot/raw")
        missing_file = client.get(f"/v1/sources/{missing_file_id}/snapshot/raw")

        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "source_not_found"
        assert no_artifact.status_code == 404
        assert no_artifact.json()["error"]["code"] == "snapshot_not_found"
        assert missing_file.status_code == 404
        assert missing_file.json()["error"]["code"] == "snapshot_file_missing"

    get_settings.cache_clear()

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
            research_service.create_run(db, task.id)
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
