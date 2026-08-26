from time import perf_counter
from time import sleep
from typing import Any, Callable, TypedDict

from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.services import research_service
from app.services.collection import CollectionSummary, FetchedSource, ParsedSource, SourceDiscovery
from app.services.collection import (
    deserialize_fetched_sources,
    deserialize_parsed_sources,
    deserialize_source_discovery,
    serialize_fetched_sources,
    serialize_parsed_sources,
    serialize_source_discovery,
)
from app.services.research_service import (
    STAGES,
    append_event,
    decode_json,
    transition_task,
)

try:
    from langgraph.graph import END, START, StateGraph
except ImportError:
    END = "__end__"
    START = "__start__"
    StateGraph = None


class ResearchWorkflowState(TypedDict):
    task_id: str
    run_id: str
    scope: dict[str, Any]
    summary: dict[str, Any]
    errors: list[str]
    current_node: str


NODE_LIFECYCLE_EVENTS = (
    "node.started",
    "node.succeeded",
    "node.failed",
    "node.skipped",
    "node.retrying",
)

WORKFLOW_NODES = (
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
)

NODE_RESUME_TARGETS = {
    "initialize_run": "plan_research",
    "plan_research": "build_search_plan",
    "build_search_plan": "discover_sources",
    "discover_sources": "discover_sources",
    "fetch_sources": "discover_sources",
    "parse_sources": "extract_evidence",
    "extract_evidence": "extract_claims",
    "extract_claims": "verify_claims",
    "verify_claims": "generate_report",
    "generate_report": "review_gate",
    "review_gate": "review_gate",
}

RETRYABLE_NODES = {
    "discover_sources": 2,
    "fetch_sources": 2,
    "parse_sources": 2,
    "extract_evidence": 2,
    "extract_claims": 2,
    "generate_report": 2,
}

MAX_CHECKPOINTS_PER_RUN = 40


class WorkflowCanceled(RuntimeError):
    pass


NON_RETRYABLE_ERROR_MARKERS = (
    "source_discovery_missing",
    "run_not_found",
    "task_not_found",
    "database_session_required",
    "report_generation_failed",
    "schema_validation_failed",
    "invalid_json_schema",
)

RETRYABLE_ERROR_MARKERS = (
    "temporary",
    "transient",
    "timeout",
    "timed out",
    "rate limit",
    "connection",
)


def is_retryable_workflow_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return False
    if any(marker in message for marker in NON_RETRYABLE_ERROR_MARKERS):
        return False
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return any(marker in message for marker in RETRYABLE_ERROR_MARKERS)


def summarize_node_input(state: ResearchWorkflowState) -> dict[str, Any]:
    scope = state.get("scope", {})
    return {
        "task_id": state["task_id"],
        "run_id": state["run_id"],
        "competitors_count": len(scope.get("competitors", [])),
        "dimensions_count": len(scope.get("dimensions", [])),
    }


def summarize_node_output(result: dict[str, Any]) -> dict[str, Any]:
    summary = result.get("summary", {})
    output_summary = {"current_node": result.get("current_node")}
    if "run_status" in summary:
        output_summary["run_status"] = summary["run_status"]
    if "current_stage" in summary:
        output_summary["current_stage"] = summary["current_stage"]
    for count_key in ("sources_created", "evidence_created", "claims_created", "claims_without_evidence", "low_confidence_claims", "conflict_claims"):
        if count_key in summary:
            output_summary[count_key] = summary[count_key]
    if "citation_coverage" in summary:
        output_summary["citation_coverage"] = summary["citation_coverage"]
    return {key: value for key, value in output_summary.items() if value is not None}


def load_source_discovery(previous_summary: dict[str, Any]) -> SourceDiscovery | None:
    discovery = previous_summary.get("collection_discovery")
    if isinstance(discovery, SourceDiscovery):
        return discovery

    discovery_state = previous_summary.get("collection_discovery_state")
    if isinstance(discovery_state, dict):
        discovery = deserialize_source_discovery(discovery_state)
        previous_summary["collection_discovery"] = discovery
        return discovery

    return None


def load_fetched_sources(previous_summary: dict[str, Any]) -> list[FetchedSource]:
    fetched_sources = previous_summary.get("fetched_sources")
    if isinstance(fetched_sources, list) and all(isinstance(item, FetchedSource) for item in fetched_sources):
        return fetched_sources

    fetched_sources_state = previous_summary.get("fetched_sources_state")
    if isinstance(fetched_sources_state, list):
        fetched_sources = deserialize_fetched_sources(fetched_sources_state)
        previous_summary["fetched_sources"] = fetched_sources
        return fetched_sources

    return []


def load_parsed_sources(previous_summary: dict[str, Any]) -> list[ParsedSource]:
    parsed_sources = previous_summary.get("parsed_sources")
    if isinstance(parsed_sources, list) and all(isinstance(item, ParsedSource) for item in parsed_sources):
        return parsed_sources

    parsed_sources_state = previous_summary.get("parsed_sources_state")
    if isinstance(parsed_sources_state, list):
        parsed_sources = deserialize_parsed_sources(parsed_sources_state)
        previous_summary["parsed_sources"] = parsed_sources
        return parsed_sources

    return []


def append_node_event(
    db: Session,
    *,
    run_id: str,
    event_type: str,
    node_name: str,
    duration_ms: int,
    input_summary: dict[str, Any],
    output_summary: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    clean_output_summary = dict(output_summary or {})
    retryable = clean_output_summary.pop("retryable", None)
    payload: dict[str, Any] = {
        "stage": node_name,
        "node_name": node_name,
        "duration_ms": duration_ms,
        "input_summary": input_summary,
        "output_summary": clean_output_summary,
    }
    if error is not None:
        payload["error"] = error
        if event_type == "node.skipped":
            payload["reason"] = error
        if event_type == "node.failed" and retryable is not None:
            payload["retryable"] = retryable

    append_event(
        db,
        run_id=run_id,
        event_type=event_type,
        stage=node_name,
        message=f"{node_name} {event_type.removeprefix('node.')}",
        payload=payload,
        severity="error" if event_type == "node.failed" else "info",
    )


def append_retry_event(
    db: Session,
    *,
    run_id: str,
    node_name: str,
    input_summary: dict[str, Any],
    attempt: int,
    max_attempts: int,
    error: str,
) -> None:
    payload = {
        "stage": node_name,
        "node_name": node_name,
        "duration_ms": 0,
        "input_summary": input_summary,
        "output_summary": {},
        "attempt": attempt,
        "max_attempts": max_attempts,
        "error": error,
    }
    append_event(
        db,
        run_id=run_id,
        event_type="node.retrying",
        stage=node_name,
        message=f"{node_name} retrying after transient failure",
        payload=payload,
    )


def ensure_not_canceled(db: Session, *, run_id: str, node_name: str, input_summary: dict[str, Any]) -> None:
    run = db.get(models.TaskRun, run_id)
    if run is None:
        return
    task = db.get(models.ResearchTask, run.task_id)
    if run.status == models.RunStatus.canceled.value or (task and task.status == models.TaskStatus.canceled.value):
        run.status = models.RunStatus.canceled.value
        run.current_stage = "canceled"
        run.finished_at = run.finished_at or models.utc_now()
        append_node_event(
            db,
            run_id=run_id,
            event_type="node.skipped",
            node_name=node_name,
            duration_ms=0,
            input_summary=input_summary,
            output_summary={"current_node": node_name, "run_status": models.RunStatus.canceled.value, "current_stage": "canceled"},
            error="task_canceled",
        )
        raise WorkflowCanceled("task_canceled")


def ensure_checkpoint_table(db: Session) -> None:
    models.WorkflowCheckpoint.__table__.create(bind=db.get_bind(), checkfirst=True)


def json_ready(value: Any) -> Any:
    try:
        research_service.encode_json(value)
    except TypeError:
        return None
    return value


def serializable_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in summary.items() if json_ready(value) is not None}


def count_task_sources(db: Session, task_id: str) -> int:
    return db.query(models.Source).filter_by(task_id=task_id).count()


def count_task_evidence(db: Session, task_id: str) -> int:
    return db.query(models.Evidence).join(models.Source).filter(models.Source.task_id == task_id).count()


def count_task_claims(db: Session, task_id: str) -> int:
    return db.query(models.Claim).filter_by(task_id=task_id).count()


def build_checkpoint_state(
    db: Session,
    *,
    state: ResearchWorkflowState,
    result: dict[str, Any],
    resume_node: str,
    node_name: str,
    retry_count: int,
) -> dict[str, Any]:
    summary = serializable_summary(dict(result.get("summary", {})))
    summary.update({"current_node": result.get("current_node")})
    summary["sources_created"] = count_task_sources(db, state["task_id"])
    summary["evidence_created"] = count_task_evidence(db, state["task_id"])
    summary["claims_created"] = count_task_claims(db, state["task_id"])
    node_retry_counts = dict(summary.get("node_retry_counts", {}))
    if retry_count:
        node_retry_counts[node_name] = retry_count
    if node_retry_counts:
        summary["node_retry_counts"] = node_retry_counts
    return {
        "task_id": state["task_id"],
        "run_id": state["run_id"],
        "scope": state.get("scope", {}),
        "summary": summary,
        "errors": list(state.get("errors", [])),
        "current_node": resume_node,
    }


def save_success_checkpoint(
    db: Session,
    *,
    run_id: str,
    node_name: str,
    input_summary: dict[str, Any],
    output_summary: dict[str, Any],
    state: ResearchWorkflowState,
    result: dict[str, Any],
    retry_count: int = 0,
) -> None:
    ensure_checkpoint_table(db)
    last_sequence = (
        db.query(models.WorkflowCheckpoint.sequence_no)
        .filter_by(run_id=run_id)
        .order_by(models.WorkflowCheckpoint.sequence_no.desc())
        .limit(1)
        .scalar()
        or 0
    )
    resume_node = NODE_RESUME_TARGETS[node_name]
    checkpoint_state = build_checkpoint_state(db, state=state, result=result, resume_node=resume_node, node_name=node_name, retry_count=retry_count)
    db.add(
        models.WorkflowCheckpoint(
            run_id=run_id,
            sequence_no=last_sequence + 1,
            node_name=node_name,
            resume_node=resume_node,
            status="succeeded",
            input_summary_json=research_service.encode_json(input_summary),
            output_summary_json=research_service.encode_json(output_summary),
            state_json=research_service.encode_json(checkpoint_state),
            retry_count=retry_count,
        )
    )
    db.flush()
    prune_workflow_checkpoints(db, run_id=run_id)
    db.commit()


def save_failed_checkpoint(
    db: Session,
    *,
    run_id: str,
    node_name: str,
    input_summary: dict[str, Any],
    retryable: bool,
    error: str,
    state: ResearchWorkflowState,
    retry_count: int = 0,
) -> None:
    ensure_checkpoint_table(db)
    last_sequence = (
        db.query(models.WorkflowCheckpoint.sequence_no)
        .filter_by(run_id=run_id)
        .order_by(models.WorkflowCheckpoint.sequence_no.desc())
        .limit(1)
        .scalar()
        or 0
    )
    checkpoint_state = {
        "task_id": state["task_id"],
        "run_id": state["run_id"],
        "scope": state.get("scope", {}),
        "summary": {
            "current_node": node_name,
            "run_status": models.RunStatus.failed.value,
            "current_stage": node_name,
            "sources_created": count_task_sources(db, state["task_id"]),
            "evidence_created": count_task_evidence(db, state["task_id"]),
            "claims_created": count_task_claims(db, state["task_id"]),
            "node_retry_counts": {node_name: retry_count} if retry_count else {},
        },
        "errors": [error],
        "current_node": node_name,
    }
    db.add(
        models.WorkflowCheckpoint(
            run_id=run_id,
            sequence_no=last_sequence + 1,
            node_name=node_name,
            resume_node=node_name,
            status="failed",
            input_summary_json=research_service.encode_json(input_summary),
            output_summary_json=research_service.encode_json({"retryable": retryable}),
            state_json=research_service.encode_json(checkpoint_state),
            error_summary=error,
            retry_count=retry_count,
        )
    )
    db.flush()
    prune_workflow_checkpoints(db, run_id=run_id)
    db.commit()


def prune_workflow_checkpoints(db: Session, *, run_id: str, max_checkpoints: int | None = None) -> None:
    keep_limit = MAX_CHECKPOINTS_PER_RUN if max_checkpoints is None else max_checkpoints
    if keep_limit <= 0:
        return

    checkpoints = (
        db.query(models.WorkflowCheckpoint)
        .filter_by(run_id=run_id)
        .order_by(models.WorkflowCheckpoint.sequence_no.desc())
        .all()
    )
    if len(checkpoints) <= keep_limit:
        return

    keep_ids = {checkpoint.id for checkpoint in checkpoints[:keep_limit]}
    latest_success = next((checkpoint for checkpoint in checkpoints if checkpoint.status == "succeeded"), None)
    if latest_success is not None:
        keep_ids.add(latest_success.id)

    for checkpoint in checkpoints:
        if checkpoint.id not in keep_ids:
            db.delete(checkpoint)


def mark_node_failed(db: Session, *, run_id: str, node_name: str, error: str) -> None:
    run = db.get(models.TaskRun, run_id)
    if run is None:
        return
    task = db.get(models.ResearchTask, run.task_id)
    run.status = models.RunStatus.failed.value
    run.current_stage = node_name
    run.error_message = error
    run.finished_at = models.utc_now()
    if task is not None:
        transition_task(task, models.TaskStatus.failed, reason=error)


def latest_success_checkpoint(db: Session, run_id: str) -> models.WorkflowCheckpoint | None:
    ensure_checkpoint_table(db)
    return (
        db.query(models.WorkflowCheckpoint)
        .filter_by(run_id=run_id, status="succeeded")
        .order_by(models.WorkflowCheckpoint.sequence_no.desc())
        .first()
    )


def instrument_node(
    db: Session | None,
    node_name: str,
    handler: Callable[[ResearchWorkflowState], dict[str, Any]],
) -> Callable[[ResearchWorkflowState], dict[str, Any]]:
    def wrapped(state: ResearchWorkflowState) -> dict[str, Any]:
        if db is None:
            return handler(state)

        input_summary = summarize_node_input(state)
        ensure_not_canceled(db, run_id=state["run_id"], node_name=node_name, input_summary=input_summary)
        max_attempts = RETRYABLE_NODES.get(node_name, 1)
        retry_count = 0
        for attempt in range(1, max_attempts + 1):
            append_node_event(
                db,
                run_id=state["run_id"],
                event_type="node.started",
                node_name=node_name,
                duration_ms=0,
                input_summary=input_summary,
            )
            started_at = perf_counter()
            try:
                result = handler(state)
            except Exception as exc:
                retryable = is_retryable_workflow_error(exc)
                if retryable and attempt < max_attempts:
                    retry_count += 1
                    append_retry_event(
                        db,
                        run_id=state["run_id"],
                        node_name=node_name,
                        input_summary=input_summary,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        error=str(exc),
                    )
                    continue

                mark_node_failed(db, run_id=state["run_id"], node_name=node_name, error=str(exc))
                save_failed_checkpoint(
                    db,
                    run_id=state["run_id"],
                    node_name=node_name,
                    input_summary=input_summary,
                    retryable=retryable,
                    error=str(exc),
                    state=state,
                    retry_count=retry_count,
                )
                append_node_event(
                    db,
                    run_id=state["run_id"],
                    event_type="node.failed",
                    node_name=node_name,
                    duration_ms=int((perf_counter() - started_at) * 1000),
                    input_summary=input_summary,
                    output_summary={"retryable": retryable},
                    error=str(exc),
                )
                raise
            break

        output_summary = summarize_node_output(result)
        append_node_event(
            db,
            run_id=state["run_id"],
            event_type="node.succeeded",
            node_name=node_name,
            duration_ms=int((perf_counter() - started_at) * 1000),
            input_summary=input_summary,
            output_summary=output_summary,
        )
        save_success_checkpoint(
            db,
            run_id=state["run_id"],
            node_name=node_name,
            input_summary=input_summary,
            output_summary=output_summary,
            state=state,
            result=result,
            retry_count=retry_count,
        )
        return result

    return wrapped


def build_research_graph(*, db: Session | None = None, delay_seconds: float = 0.0, start_at: str = "initialize_run"):
    if StateGraph is None:
        raise RuntimeError(
            "LangGraph is required to run the research workflow. "
            "Install dependencies with `pip install -r backend/requirements.txt`."
        )
    if start_at not in WORKFLOW_NODES:
        raise ValueError(f"unknown_workflow_start:{start_at}")

    graph = StateGraph(ResearchWorkflowState)

    def get_run_and_task(state: ResearchWorkflowState) -> tuple[models.TaskRun, models.ResearchTask]:
        if db is None:
            raise RuntimeError("database_session_required")

        run = db.get(models.TaskRun, state["run_id"])
        if run is None:
            raise ValueError("run_not_found")
        task = db.get(models.ResearchTask, run.task_id)
        if task is None:
            raise ValueError("task_not_found")
        return run, task

    def build_state_update(
        *,
        next_node: str,
        run: models.TaskRun,
        extra_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        summary = dict(extra_summary or {})
        summary.update({"run_status": run.status, "current_stage": run.current_stage})
        return {"current_node": next_node, "summary": summary, "errors": []}

    def write_domain_event(
        *,
        run: models.TaskRun,
        event_type: str,
        stage: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if db is None:
            return
        run.current_stage = stage
        append_event(db, run_id=run.id, event_type=event_type, stage=stage, message=message, payload=payload)
        if delay_seconds:
            sleep(delay_seconds)

    def initialize_run(state: ResearchWorkflowState) -> dict[str, Any]:
        if db is None:
            return {"current_node": "plan_research"}

        run, task = get_run_and_task(state)
        run.status = models.RunStatus.running.value
        run.current_stage = "plan_research"
        run.started_at = models.utc_now()
        transition_task(task, models.TaskStatus.running)
        db.commit()
        return build_state_update(next_node="plan_research", run=run)

    def plan_research(state: ResearchWorkflowState) -> dict[str, Any]:
        if db is None:
            return {"current_node": "build_search_plan"}

        run, _task = get_run_and_task(state)
        event_type, stage, message = STAGES[0]
        write_domain_event(run=run, event_type=event_type, stage=stage, message=message)
        return build_state_update(next_node="build_search_plan", run=run)

    def build_search_plan(state: ResearchWorkflowState) -> dict[str, Any]:
        if db is None:
            return {"current_node": "discover_sources"}

        run, task = get_run_and_task(state)
        scope = dict(state.get("scope", {}))
        competitors = [str(item).strip() for item in scope.get("competitors", []) if str(item).strip()]
        dimensions = [str(item).strip() for item in scope.get("dimensions", []) if str(item).strip()]
        query = " ".join(part for part in [task.prompt, " ".join(competitors), " ".join(dimensions)] if part).strip()
        search_plan = {
            "query": query,
            "competitors": competitors,
            "dimensions": dimensions,
            "source_preferences": list(scope.get("source_preferences", [])),
            "source_type_priority": list(scope.get("source_type_priority", ["official", "docs", "news", "web"])),
            "budget": dict(scope.get("budget", {})),
        }
        summary = {
            "search_plan": search_plan,
            "search_terms_count": len(search_plan["query"].split()) if search_plan["query"] else 0,
            "source_preferences_count": len(search_plan["source_preferences"]),
        }
        return build_state_update(next_node="discover_sources", run=run, extra_summary=summary)

    def discover_sources(state: ResearchWorkflowState) -> dict[str, Any]:
        if db is None:
            return {"current_node": "fetch_sources"}

        run, task = get_run_and_task(state)
        previous_summary = dict(state.get("summary", {}))
        search_plan = previous_summary.get("search_plan")

        def write_event(event_type: str, stage: str, message: str, payload: dict[str, Any] | None = None) -> None:
            write_domain_event(run=run, event_type=event_type, stage=stage, message=message, payload=payload)

        discovery = research_service.discover_research_sources(
            db,
            task=task,
            settings=get_settings(),
            write_event=write_event,
            search_plan=search_plan if isinstance(search_plan, dict) else None,
        )
        summary: dict[str, Any] = {
            **previous_summary,
            "collection_discovery": discovery,
            "collection_discovery_state": serialize_source_discovery(discovery),
            "collection_summary": discovery.summary,
            "searched": discovery.summary.searched,
            "sources_created": discovery.summary.sources_created,
            "evidence_created": discovery.summary.evidence_created,
            "demo_seeded": False,
        }
        return build_state_update(next_node="fetch_sources", run=run, extra_summary=summary)

    def fetch_sources(state: ResearchWorkflowState) -> dict[str, Any]:
        if db is None:
            return {"current_node": "parse_sources"}

        run, _task = get_run_and_task(state)
        previous_summary = dict(state.get("summary", {}))
        discovery = load_source_discovery(previous_summary)
        if not isinstance(discovery, SourceDiscovery):
            raise RuntimeError("source_discovery_missing")

        def write_event(event_type: str, stage: str, message: str, payload: dict[str, Any] | None = None) -> None:
            write_domain_event(run=run, event_type=event_type, stage=stage, message=message, payload=payload)

        fetched_sources = research_service.fetch_research_sources(discovery=discovery, settings=get_settings(), write_event=write_event)
        previous_summary["fetched_sources"] = fetched_sources
        previous_summary["fetched_sources_state"] = serialize_fetched_sources(fetched_sources)
        previous_summary["collection_summary"] = discovery.summary
        return build_state_update(next_node="parse_sources", run=run, extra_summary=previous_summary)

    def parse_sources(state: ResearchWorkflowState) -> dict[str, Any]:
        if db is None:
            return {"current_node": "extract_evidence"}

        run, task = get_run_and_task(state)
        previous_summary = dict(state.get("summary", {}))
        discovery = load_source_discovery(previous_summary)
        if not isinstance(discovery, SourceDiscovery):
            raise RuntimeError("source_discovery_missing")
        fetched_sources = load_fetched_sources(previous_summary)

        def write_event(event_type: str, stage: str, message: str, payload: dict[str, Any] | None = None) -> None:
            write_domain_event(run=run, event_type=event_type, stage=stage, message=message, payload=payload)

        parsed_sources = research_service.parse_research_sources(
            db,
            task=task,
            discovery=discovery,
            fetched_sources=fetched_sources,
            settings=get_settings(),
            write_event=write_event,
        )
        previous_summary["parsed_sources"] = parsed_sources
        previous_summary["parsed_sources_state"] = serialize_parsed_sources(parsed_sources)
        previous_summary["collection_summary"] = discovery.summary
        previous_summary["sources_created"] = discovery.summary.sources_created
        return build_state_update(next_node="extract_evidence", run=run, extra_summary=previous_summary)

    def extract_evidence(state: ResearchWorkflowState) -> dict[str, Any]:
        if db is None:
            return {"current_node": "extract_claims"}

        run, task = get_run_and_task(state)
        previous_summary = dict(state.get("summary", {}))
        discovery = load_source_discovery(previous_summary)
        if not isinstance(discovery, SourceDiscovery):
            raise RuntimeError("source_discovery_missing")
        parsed_sources = load_parsed_sources(previous_summary)

        def write_event(event_type: str, stage: str, message: str, payload: dict[str, Any] | None = None) -> None:
            write_domain_event(run=run, event_type=event_type, stage=stage, message=message, payload=payload)

        try:
            collection_summary = research_service.extract_research_evidence(
                db,
                task=task,
                discovery=discovery,
                parsed_sources=parsed_sources,
                settings=get_settings(),
                write_event=write_event,
            )
        except TypeError as exc:
            if "unexpected keyword argument 'settings'" not in str(exc):
                raise
            collection_summary = research_service.extract_research_evidence(
                db,
                task=task,
                discovery=discovery,
                parsed_sources=parsed_sources,
                write_event=write_event,
            )
        summary: dict[str, Any] = dict(previous_summary)
        summary.update(
            {
                "collection_summary": collection_summary,
                "searched": collection_summary.searched,
                "sources_created": collection_summary.sources_created,
                "evidence_created": collection_summary.evidence_created,
                "demo_seeded": False,
            }
        )
        if collection_summary.evidence_created == 0:
            for event_type, stage, message in STAGES[1:3]:
                write_domain_event(run=run, event_type=event_type, stage=stage, message=message)
            research_service.seed_demo_research_objects(db, task.id)
            summary["demo_seeded"] = True
            summary["sources_created"] = db.query(models.Source).filter_by(task_id=task.id).count()
            summary["evidence_created"] = db.query(models.Evidence).join(models.Source).filter(models.Source.task_id == task.id).count()
            event_type, stage, message = STAGES[3]
            write_domain_event(run=run, event_type=event_type, stage=stage, message=message)

        return build_state_update(next_node="extract_claims", run=run, extra_summary=summary)

    def extract_claims(state: ResearchWorkflowState) -> dict[str, Any]:
        if db is None:
            return {"current_node": "verify_claims"}

        run, task = get_run_and_task(state)
        previous_summary = state.get("summary", {})
        if previous_summary.get("demo_seeded"):
            claims_created = db.query(models.Claim).filter_by(task_id=task.id).count()
        elif previous_summary.get("evidence_created", 0):
            claim_result = research_service.extract_and_store_claims(db, task=task, settings=get_settings())
            claims_created = len(claim_result.claims)
        else:
            claims_created = 0

        summary = dict(previous_summary)
        summary["claims_created"] = claims_created
        return build_state_update(next_node="verify_claims", run=run, extra_summary=summary)

    def verify_claims(state: ResearchWorkflowState) -> dict[str, Any]:
        if db is None:
            return {"current_node": "generate_report"}

        run, task = get_run_and_task(state)
        previous_summary = dict(state.get("summary", {}))
        verification_summary = research_service.verify_claims(db, task=task)
        previous_summary.update(verification_summary)
        run.current_stage = "verify_claims"
        append_event(
            db,
            run_id=run.id,
            event_type="claim.created",
            stage="verify_claims",
            message=(
                f"已从 Evidence 生成 {verification_summary['claims_created']} 条结构化 Claim，"
                "并完成引用完整性和置信度检查。"
            ),
            payload={**verification_summary, "extractor": "llm_or_rule_based"},
        )
        return build_state_update(next_node="generate_report", run=run, extra_summary=previous_summary)

    def generate_report(state: ResearchWorkflowState) -> dict[str, Any]:
        if db is None:
            return {"current_node": "review_gate"}

        run, task = get_run_and_task(state)
        previous_summary = state.get("summary", {})
        collection_summary = previous_summary.get("collection_summary")
        if not isinstance(collection_summary, CollectionSummary):
            collection_summary = CollectionSummary(
                provider=get_settings().search_provider,
                searched=bool(previous_summary.get("searched")),
                sources_created=previous_summary.get("sources_created", 0),
                evidence_created=previous_summary.get("evidence_created", 0),
            )

        if previous_summary.get("demo_seeded"):
            event_type, stage, message = STAGES[5]
            write_domain_event(run=run, event_type=event_type, stage=stage, message=message)
        else:
            research_service.generate_report_with_retry(db, task=task, run=run, summary=collection_summary)

        run.current_stage = "generate_report"
        has_report_created_event = db.query(models.ResearchEvent.id).filter_by(run_id=run.id, type="report.created").first() is not None
        if not has_report_created_event:
            append_event(
                db,
                run_id=run.id,
                event_type="report.created",
                stage="generate_report",
                message="已生成基于 Evidence 和 Claim 的结构化报告草稿。",
                payload={
                    "sources_created": previous_summary.get("sources_created", collection_summary.sources_created),
                    "evidence_created": previous_summary.get("evidence_created", collection_summary.evidence_created),
                    "claims_created": previous_summary.get("claims_created", 0),
                },
            )
        return build_state_update(next_node="review_gate", run=run, extra_summary=dict(previous_summary))

    def review_gate(state: ResearchWorkflowState) -> dict[str, Any]:
        if db is None:
            return {"current_node": "review_gate"}

        run, task = get_run_and_task(state)
        unresolved_risky_claims = research_service.get_unresolved_risky_claims(db, task.id)
        if not unresolved_risky_claims:
            run.status = models.RunStatus.completed.value
            run.current_stage = "completed"
            transition_task(task, models.TaskStatus.completed)
            run.finished_at = models.utc_now()
            append_event(
                db,
                run_id=run.id,
                event_type="task.completed",
                stage="completed",
                message="All claims are ready for delivery; the research task is complete.",
            )
            db.commit()
            db.refresh(run)
            return build_state_update(next_node="review_gate", run=run, extra_summary=dict(state.get("summary", {})))

        run.status = models.RunStatus.waiting_review.value
        run.current_stage = "review_gate"
        has_review_required_event = (
            db.query(models.ResearchEvent.id)
            .filter_by(run_id=run.id, type="review.required")
            .first()
            is not None
        )
        if not has_review_required_event:
            append_event(
                db,
                run_id=run.id,
                event_type="review.required",
                stage="review_gate",
                message="Risky claims require human review before final delivery.",
                payload={"unresolved_risky_claims": len(unresolved_risky_claims)},
            )
        transition_task(task, models.TaskStatus.waiting_review)
        run.finished_at = models.utc_now()
        db.commit()
        db.refresh(run)
        return build_state_update(next_node="review_gate", run=run, extra_summary=dict(state.get("summary", {})))

    graph.add_node("initialize_run", instrument_node(db, "initialize_run", initialize_run))
    graph.add_node("plan_research", instrument_node(db, "plan_research", plan_research))
    graph.add_node("build_search_plan", instrument_node(db, "build_search_plan", build_search_plan))
    graph.add_node("discover_sources", instrument_node(db, "discover_sources", discover_sources))
    graph.add_node("fetch_sources", instrument_node(db, "fetch_sources", fetch_sources))
    graph.add_node("parse_sources", instrument_node(db, "parse_sources", parse_sources))
    graph.add_node("extract_evidence", instrument_node(db, "extract_evidence", extract_evidence))
    graph.add_node("extract_claims", instrument_node(db, "extract_claims", extract_claims))
    graph.add_node("verify_claims", instrument_node(db, "verify_claims", verify_claims))
    graph.add_node("generate_report", instrument_node(db, "generate_report", generate_report))
    graph.add_node("review_gate", instrument_node(db, "review_gate", review_gate))
    graph.add_edge(START, start_at)
    graph.add_edge("initialize_run", "plan_research")
    graph.add_edge("plan_research", "build_search_plan")
    graph.add_edge("build_search_plan", "discover_sources")
    graph.add_edge("discover_sources", "fetch_sources")
    graph.add_edge("fetch_sources", "parse_sources")
    graph.add_edge("parse_sources", "extract_evidence")
    graph.add_edge("extract_evidence", "extract_claims")
    graph.add_edge("extract_claims", "verify_claims")
    graph.add_edge("verify_claims", "generate_report")
    graph.add_edge("generate_report", "review_gate")
    graph.add_edge("review_gate", END)
    return graph.compile()


def rebuild_resume_state(db: Session, run: models.TaskRun, task: models.ResearchTask, checkpoint: models.WorkflowCheckpoint) -> ResearchWorkflowState:
    checkpoint_state = decode_json(checkpoint.state_json)
    summary = dict(checkpoint_state.get("summary", {}))
    summary["sources_created"] = count_task_sources(db, task.id)
    summary["evidence_created"] = count_task_evidence(db, task.id)
    summary["claims_created"] = count_task_claims(db, task.id)
    summary["run_status"] = models.RunStatus.running.value
    summary["current_stage"] = checkpoint.resume_node
    return ResearchWorkflowState(
        task_id=task.id,
        run_id=run.id,
        scope=decode_json(run.input_snapshot_json),
        summary=summary,
        errors=[],
        current_node=checkpoint.resume_node,
    )


def prepare_run_for_resume(db: Session, run: models.TaskRun, task: models.ResearchTask, start_node: str) -> None:
    if task.status == models.TaskStatus.failed.value:
        transition_task(task, models.TaskStatus.queued)
    if task.status == models.TaskStatus.queued.value:
        transition_task(task, models.TaskStatus.running)
    run.status = models.RunStatus.running.value
    run.current_stage = start_node
    run.error_message = None
    run.finished_at = None
    db.commit()


def run_research_workflow(db: Session, run_id: str, delay_seconds: float = 0.0, *, resume: bool = False) -> models.TaskRun:
    run = db.get(models.TaskRun, run_id)
    if run is None:
        raise ValueError("run_not_found")
    task = db.get(models.ResearchTask, run.task_id)
    if task is None:
        raise ValueError("task_not_found")

    checkpoint = latest_success_checkpoint(db, run.id) if resume else None
    if checkpoint is None:
        start_node = "initialize_run"
        initial_state: ResearchWorkflowState = {
            "task_id": task.id,
            "run_id": run.id,
            "scope": decode_json(run.input_snapshot_json),
            "summary": {},
            "errors": [],
            "current_node": "initialize_run",
        }
    else:
        start_node = checkpoint.resume_node
        prepare_run_for_resume(db, run, task, start_node)
        initial_state = rebuild_resume_state(db, run, task, checkpoint)

    graph = build_research_graph(db=db, delay_seconds=delay_seconds, start_at=start_node)
    try:
        graph.invoke(initial_state)
    except WorkflowCanceled:
        db.refresh(run)
        return run

    db.refresh(run)
    return run
