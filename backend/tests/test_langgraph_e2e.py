"""LangGraph 集成测试（清单 704）：端到端全链路——demo 流程/无 Tavily Key 手动 URL/无 LLM Key 规则降级/后台执行与 review 闭环/报告导出/Celery 入队与自动恢复/rerun 与 resume。从 test_api_contract.py 按模块拆出。"""


import pytest
from fastapi.testclient import TestClient

from app import models
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.main import app
from app.services import collection, research_service
from app.services.analysis import llm
from app.services.fetching.fetcher import FetchResult


@pytest.fixture(autouse=True)
def disable_real_search(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "")
    get_settings.cache_clear()
    init_db()
    yield
    get_settings.cache_clear()


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
            "research_plan",
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
        assert [event["stage"] for event in domain_event_body] == [
            "initialize_run",
            "plan_research",
            "discover_sources",
            "discover_sources",
            "fetch_source",
            "extract_evidence",
            "extract_evidence",
            "extract_evidence",
            "verify_claims",
            "verify_claims",
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
    from app.api import tasks as routes

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
    from app.api import tasks as routes

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
    from app.api import tasks as routes
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
