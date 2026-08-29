"""工作流节点测试（清单 703）：research_graph 节点级行为——节点生命周期事件/成功与失败 checkpoint/断点恢复/节点重试边界/review 门控/取消与独立失败边界。从 test_api_contract.py 按模块拆出。"""

import pytest

from app import models
from app.config import Settings, get_settings
from app.db import SessionLocal, init_db
from app.services import collection, research_service
from app.services.analysis import claim_extractor
from app.services.fetching import fetcher as fetcher_module
from app.services.fetching.fetcher import FetchResult
from app.services.parsing import html_parser
from app.services.search.base import SearchResult


@pytest.fixture(autouse=True)
def disable_real_search(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "")
    get_settings.cache_clear()
    init_db()
    yield
    get_settings.cache_clear()


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
            "report.section_updated",
            "planning.started",
            "search.skipped",
            "search.started",
            "source.found",
            "report.section_updated",
            "report.section_updated",
            "evidence.created",
            "claim.created",
            "claim.verified",
            "claim.conflict_detected",
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
