import re
from collections.abc import Generator

from sqlalchemy import Connection, Engine, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine_kwargs: dict = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
elif settings.database_url.startswith("mysql"):
    # MySQL closes idle connections after wait_timeout; recycle proactively.
    engine_kwargs.update({"pool_recycle": 3600, "pool_size": 10, "max_overflow": 20})

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    apply_mvp_schema_upgrades()


def apply_mvp_schema_upgrades(bind: Engine | Connection | None = None) -> None:
    target = bind or engine
    inspector = inspect(target)
    table_names = inspector.get_table_names()
    if "task_runs" not in table_names:
        return

    if isinstance(target, Connection):
        _apply_mvp_schema_upgrades(target, inspector, table_names)
    else:
        with target.begin() as connection:
            _apply_mvp_schema_upgrades(connection, inspector, table_names)


def _apply_mvp_schema_upgrades(connection, inspector, table_names) -> None:
    add_column_if_missing(connection, inspector, "research_tasks", "current_run_id", "VARCHAR(40)")
    add_column_if_missing(connection, inspector, "research_tasks", "workspace_id", "VARCHAR(40) DEFAULT 'default'")
    add_column_if_missing(connection, inspector, "research_tasks", "failure_reason", "TEXT")
    add_column_if_missing(connection, inspector, "research_tasks", "confirmed_at", "DATETIME")
    add_column_if_missing(connection, inspector, "research_tasks", "queued_at", "DATETIME")
    add_column_if_missing(connection, inspector, "research_tasks", "completed_at", "DATETIME")
    connection.execute(text("UPDATE research_tasks SET workspace_id = 'default' WHERE workspace_id IS NULL OR workspace_id = ''"))

    add_column_if_missing(connection, inspector, "task_runs", "error_message", "TEXT")
    add_column_if_missing(connection, inspector, "task_runs", "input_snapshot_json", "TEXT DEFAULT '{}'")
    add_column_if_missing(connection, inspector, "task_runs", "queued_at", "DATETIME")
    add_column_if_missing(connection, inspector, "task_runs", "priority", "INTEGER DEFAULT 5")
    connection.execute(text("UPDATE task_runs SET input_snapshot_json = '{}' WHERE input_snapshot_json IS NULL"))
    connection.execute(text("UPDATE task_runs SET queued_at = COALESCE(started_at, finished_at, CURRENT_TIMESTAMP) WHERE queued_at IS NULL"))
    connection.execute(text("UPDATE task_runs SET priority = 5 WHERE priority IS NULL"))

    add_column_if_missing(connection, inspector, "research_events", "severity", "VARCHAR(20) DEFAULT 'info'")
    add_column_if_missing(connection, inspector, "research_events", "actor", "VARCHAR(80) DEFAULT 'system'")
    connection.execute(text("UPDATE research_events SET severity = 'info' WHERE severity IS NULL"))
    connection.execute(text("UPDATE research_events SET actor = 'system' WHERE actor IS NULL"))

    add_column_if_missing(connection, inspector, "sources", "is_primary", "BOOLEAN DEFAULT 0")
    add_column_if_missing(connection, inspector, "sources", "social_platform", "VARCHAR(40)")
    add_column_if_missing(connection, inspector, "sources", "sentiment", "VARCHAR(40)")
    add_column_if_missing(connection, inspector, "sources", "heat_score", "FLOAT")
    add_column_if_missing(connection, inspector, "sources", "interaction_metrics_json", "TEXT DEFAULT '{}'")
    connection.execute(text("UPDATE sources SET interaction_metrics_json = '{}' WHERE interaction_metrics_json IS NULL OR interaction_metrics_json = ''"))

    add_column_if_missing(connection, inspector, "evidence", "evidence_hash", "VARCHAR(80)")
    add_column_if_missing(connection, inspector, "evidence", "extraction_method", "VARCHAR(80) DEFAULT 'demo_seed'")
    add_column_if_missing(connection, inspector, "evidence", "source_version", "INTEGER DEFAULT 1")
    connection.execute(text("UPDATE evidence SET evidence_hash = id WHERE evidence_hash IS NULL OR evidence_hash = ''"))
    connection.execute(text("UPDATE evidence SET extraction_method = 'demo_seed' WHERE extraction_method IS NULL"))
    connection.execute(text("UPDATE evidence SET source_version = 1 WHERE source_version IS NULL"))

    add_column_if_missing(connection, inspector, "claims", "dimension", "VARCHAR(120) DEFAULT 'general'")
    add_column_if_missing(connection, inspector, "claims", "evidence_coverage", "FLOAT DEFAULT 0")
    connection.execute(text("UPDATE claims SET dimension = claim_type WHERE dimension IS NULL OR dimension = 'general'"))
    connection.execute(text("UPDATE claims SET evidence_coverage = 0 WHERE evidence_coverage IS NULL"))

    add_column_if_missing(connection, inspector, "review_decisions", "previous_status", "VARCHAR(40)")
    add_column_if_missing(connection, inspector, "review_decisions", "resulting_status", "VARCHAR(40)")

    add_column_if_missing(connection, inspector, "reports", "input_snapshot_json", "TEXT DEFAULT '{}'")
    add_column_if_missing(connection, inspector, "reports", "generated_at", "DATETIME")
    connection.execute(text("UPDATE reports SET input_snapshot_json = '{}' WHERE input_snapshot_json IS NULL"))

    if "source_artifacts" in table_names:
        add_column_if_missing(connection, inspector, "source_artifacts", "content_type", "VARCHAR(120) DEFAULT 'text/html; charset=utf-8'")
        add_column_if_missing(connection, inspector, "source_artifacts", "size_bytes", "INTEGER DEFAULT 0")
        connection.execute(text("UPDATE source_artifacts SET content_type = 'text/html; charset=utf-8' WHERE content_type IS NULL OR content_type = ''"))
        connection.execute(text("UPDATE source_artifacts SET size_bytes = 0 WHERE size_bytes IS NULL"))

    if "report_artifacts" in table_names:
        add_column_if_missing(connection, inspector, "report_artifacts", "content_type", "VARCHAR(120) DEFAULT 'application/octet-stream'")
        add_column_if_missing(connection, inspector, "report_artifacts", "size_bytes", "INTEGER DEFAULT 0")
        connection.execute(text("UPDATE report_artifacts SET content_type = 'application/octet-stream' WHERE content_type IS NULL OR content_type = ''"))
        connection.execute(text("UPDATE report_artifacts SET size_bytes = 0 WHERE size_bytes IS NULL"))

    create_unique_index_if_clean(connection, "sources", "ux_sources_task_content_hash", ["task_id", "content_hash"])
    create_unique_index_if_clean(connection, "source_artifacts", "ux_source_artifacts_source_type", ["source_id", "artifact_type"])
    if "report_artifacts" in table_names:
        create_unique_index_if_clean(connection, "report_artifacts", "ux_report_artifacts_report_type", ["report_id", "artifact_type"])
    create_unique_index_if_clean(connection, "evidence", "ux_evidence_source_hash", ["source_id", "evidence_hash"])
    create_unique_index_if_clean(connection, "claims", "ux_claims_task_fact", ["task_id", "subject", "predicate", "claim_type"])
    create_unique_index_if_clean(connection, "claim_evidence", "ux_claim_evidence_relation", ["claim_id", "evidence_id", "relation"])
    create_unique_index_if_clean(connection, "reports", "ux_reports_task_version", ["task_id", "version"])
    create_unique_index_if_clean(connection, "report_sections", "ux_report_sections_order", ["report_id", "order_no"])


def add_column_if_missing(connection, inspector, table_name: str, column_name: str, definition: str) -> None:
    columns = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name not in columns:
        definition = column_definition_for_dialect(definition, connection.dialect.name)
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))


def column_definition_for_dialect(definition: str, dialect_name: str) -> str:
    """MySQL does not allow literal DEFAULT clauses on TEXT columns."""
    if dialect_name == "mysql" and definition.upper().startswith("TEXT"):
        return re.split(r"\s+DEFAULT\s+", definition, maxsplit=1)[0]
    return definition


def create_unique_index_if_clean(connection, table_name: str, index_name: str, columns: list[str]) -> None:
    if _has_equivalent_unique_index(connection, table_name, index_name, columns):
        return
    column_list = ", ".join(columns)
    duplicate_count = connection.execute(
        text(
            f"""
            SELECT COUNT(*) FROM (
              SELECT {column_list}
              FROM {table_name}
              GROUP BY {column_list}
              HAVING COUNT(*) > 1
            ) AS duplicate_rows
            """
        )
    ).scalar_one()
    if duplicate_count == 0:
        connection.execute(text(create_unique_index_sql(connection.dialect.name, index_name, table_name, column_list)))


def _has_equivalent_unique_index(connection, table_name: str, index_name: str, columns: list[str]) -> bool:
    for index in inspect(connection).get_indexes(table_name):
        if not index.get("unique", False):
            continue
        index_columns = set(index.get("column_names") or [])
        if index.get("name") == index_name or index_columns == set(columns):
            return True
    return False


def create_unique_index_sql(dialect_name: str, index_name: str, table_name: str, column_list: str) -> str:
    """SQLite supports IF NOT EXISTS; MySQL does not, callers must check first."""
    if_not_exists = "IF NOT EXISTS " if dialect_name == "sqlite" else ""
    return f"CREATE UNIQUE INDEX {if_not_exists}{index_name} ON {table_name} ({column_list})"
