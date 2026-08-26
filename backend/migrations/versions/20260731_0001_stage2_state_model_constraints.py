"""stage2 state model constraints

Revision ID: 20260731_0001
Revises:
Create Date: 2026-07-31 00:00:00

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260731_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if not _has_table("research_tasks"):
        return

    _add_column_if_missing("research_tasks", "current_run_id", sa.Column("current_run_id", sa.String(length=40), nullable=True))
    _add_column_if_missing("research_tasks", "failure_reason", sa.Column("failure_reason", sa.Text(), nullable=True))
    _add_column_if_missing("research_tasks", "confirmed_at", sa.Column("confirmed_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("research_tasks", "queued_at", sa.Column("queued_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("research_tasks", "completed_at", sa.Column("completed_at", sa.DateTime(), nullable=True))
    _create_index_if_missing("research_tasks", "ix_research_tasks_current_run_id", ["current_run_id"])

    _add_column_if_missing("task_runs", "input_snapshot_json", sa.Column("input_snapshot_json", sa.Text(), nullable=True))
    _add_column_if_missing("task_runs", "queued_at", sa.Column("queued_at", sa.DateTime(), nullable=True))

    _add_column_if_missing("research_events", "severity", sa.Column("severity", sa.String(length=20), nullable=True))
    _add_column_if_missing("research_events", "actor", sa.Column("actor", sa.String(length=80), nullable=True))
    _create_index_if_missing("research_events", "ix_research_events_severity", ["severity"])

    _add_column_if_missing("sources", "is_primary", sa.Column("is_primary", sa.Boolean(), nullable=True))
    _add_column_if_missing("sources", "social_platform", sa.Column("social_platform", sa.String(length=40), nullable=True))
    _add_column_if_missing("sources", "sentiment", sa.Column("sentiment", sa.String(length=40), nullable=True))
    _add_column_if_missing("sources", "heat_score", sa.Column("heat_score", sa.Float(), nullable=True))
    _add_column_if_missing("sources", "interaction_metrics_json", sa.Column("interaction_metrics_json", sa.Text(), nullable=True))
    _create_index_if_missing("sources", "ux_sources_task_content_hash", ["task_id", "content_hash"], unique=True)

    _add_column_if_missing("evidence", "evidence_hash", sa.Column("evidence_hash", sa.String(length=80), nullable=True))
    _add_column_if_missing("evidence", "extraction_method", sa.Column("extraction_method", sa.String(length=80), nullable=True))
    _add_column_if_missing("evidence", "source_version", sa.Column("source_version", sa.Integer(), nullable=True))
    _create_index_if_missing("evidence", "ix_evidence_evidence_hash", ["evidence_hash"])
    _create_index_if_missing("evidence", "ux_evidence_source_hash", ["source_id", "evidence_hash"], unique=True)

    _add_column_if_missing("claims", "dimension", sa.Column("dimension", sa.String(length=120), nullable=True))
    _add_column_if_missing("claims", "evidence_coverage", sa.Column("evidence_coverage", sa.Float(), nullable=True))
    _create_index_if_missing("claims", "ix_claims_dimension", ["dimension"])
    _create_index_if_missing("claims", "ux_claims_task_fact", ["task_id", "subject", "predicate", "claim_type"], unique=True)

    _add_column_if_missing("review_decisions", "previous_status", sa.Column("previous_status", sa.String(length=40), nullable=True))
    _add_column_if_missing("review_decisions", "resulting_status", sa.Column("resulting_status", sa.String(length=40), nullable=True))

    _add_column_if_missing("reports", "input_snapshot_json", sa.Column("input_snapshot_json", sa.Text(), nullable=True))
    _add_column_if_missing("reports", "generated_at", sa.Column("generated_at", sa.DateTime(), nullable=True))
    _create_index_if_missing("reports", "ux_reports_task_version", ["task_id", "version"], unique=True)

    _create_index_if_missing("source_artifacts", "ux_source_artifacts_source_type", ["source_id", "artifact_type"], unique=True)
    _create_index_if_missing("claim_evidence", "ux_claim_evidence_relation", ["claim_id", "evidence_id", "relation"], unique=True)
    _create_index_if_missing("report_sections", "ux_report_sections_order", ["report_id", "order_no"], unique=True)


def downgrade() -> None:
    raise NotImplementedError("Stage 2 is a baseline migration and is not reversible.")


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _add_column_if_missing(table_name: str, column_name: str, column: sa.Column) -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table_name)}
    if column_name not in columns:
        op.add_column(table_name, column)


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str], *, unique: bool = False) -> None:
    inspector = sa.inspect(op.get_bind())
    existing_indexes = inspector.get_indexes(table_name)
    if any(item["name"] == index_name for item in existing_indexes):
        return
    existing_unique_constraints = inspector.get_unique_constraints(table_name)
    if unique and any(set(item["column_names"]) == set(columns) for item in existing_unique_constraints):
        return
    op.create_index(index_name, table_name, columns, unique=unique)
