from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class TaskStatus(str, Enum):
    draft = "draft"
    confirmed = "confirmed"
    queued = "queued"
    running = "running"
    waiting_review = "waiting_review"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    waiting_review = "waiting_review"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"


class ClaimStatus(str, Enum):
    verified = "verified"
    low_confidence = "low_confidence"
    conflict = "conflict"
    undisclosed = "undisclosed"
    needs_evidence = "needs_evidence"


class ResearchTask(Base):
    __tablename__ = "research_tasks"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("task"))
    title: Mapped[str] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text)
    scope_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(40), default=TaskStatus.draft.value, index=True)
    workspace_id: Mapped[str] = mapped_column(String(40), default="default", index=True)
    current_run_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(80), default="local-user")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    runs: Mapped[list["TaskRun"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    sources: Mapped[list["Source"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    claims: Mapped[list["Claim"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class CompetitorProfile(Base):
    __tablename__ = "competitor_profiles"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_competitor_profile_workspace_name"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("comp"))
    workspace_id: Mapped[str] = mapped_column(String(40), default="default", index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    category: Mapped[str] = mapped_column(String(120), default="general")
    description: Mapped[str] = mapped_column(Text, default="")
    homepage_url: Mapped[str] = mapped_column(String(2048), default="")
    source_urls_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class TaskRun(Base):
    __tablename__ = "task_runs"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("run"))
    task_id: Mapped[str] = mapped_column(ForeignKey("research_tasks.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default=RunStatus.queued.value, index=True)
    current_stage: Mapped[str] = mapped_column(String(80), default="queued")
    iteration_count: Mapped[int] = mapped_column(Integer, default=0)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    input_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    task: Mapped[ResearchTask] = relationship(back_populates="runs")
    events: Mapped[list["ResearchEvent"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    checkpoints: Mapped[list["WorkflowCheckpoint"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class ResearchEvent(Base):
    __tablename__ = "research_events"
    __table_args__ = (UniqueConstraint("run_id", "sequence_no", name="uq_run_sequence"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("evt"))
    run_id: Mapped[str] = mapped_column(ForeignKey("task_runs.id"), index=True)
    sequence_no: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(80), index=True)
    stage: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    severity: Mapped[str] = mapped_column(String(20), default="info", index=True)
    actor: Mapped[str] = mapped_column(String(80), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    run: Mapped[TaskRun] = relationship(back_populates="events")


class WorkflowCheckpoint(Base):
    __tablename__ = "workflow_checkpoints"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence_no", name="uq_workflow_checkpoint_sequence"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("ckpt"))
    run_id: Mapped[str] = mapped_column(ForeignKey("task_runs.id"), index=True)
    sequence_no: Mapped[int] = mapped_column(Integer)
    node_name: Mapped[str] = mapped_column(String(80), index=True)
    resume_node: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), default="succeeded", index=True)
    input_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    output_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    state_json: Mapped[str] = mapped_column(Text, default="{}")
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    run: Mapped[TaskRun] = relationship(back_populates="checkpoints")


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("task_id", "content_hash", name="uq_source_task_content_hash"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("src"))
    task_id: Mapped[str] = mapped_column(ForeignKey("research_tasks.id"), index=True)
    url: Mapped[str] = mapped_column(String(2048))
    canonical_url: Mapped[str] = mapped_column(String(2048))
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(255))
    publisher: Mapped[str] = mapped_column(String(120))
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    social_platform: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    sentiment: Mapped[str | None] = mapped_column(String(40), nullable=True)
    heat_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    interaction_metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    content_hash: Mapped[str] = mapped_column(String(80), index=True)
    index_status: Mapped[str] = mapped_column(String(40), default="pending")
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    task: Mapped[ResearchTask] = relationship(back_populates="sources")
    evidence_items: Mapped[list["Evidence"]] = relationship(back_populates="source", cascade="all, delete-orphan")
    artifacts: Mapped[list["SourceArtifact"]] = relationship(back_populates="source", cascade="all, delete-orphan")


class SourceArtifact(Base):
    __tablename__ = "source_artifacts"
    __table_args__ = (
        UniqueConstraint("source_id", "artifact_type", name="uq_source_artifact_type"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("art"))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(40))
    object_key: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(80))
    content_type: Mapped[str] = mapped_column(String(120), default="text/html; charset=utf-8")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    source: Mapped[Source] = relationship(back_populates="artifacts")


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("source_id", "evidence_hash", name="uq_evidence_source_hash"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("ev"))
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    quote: Mapped[str] = mapped_column(Text)
    locator_json: Mapped[str] = mapped_column(Text, default="{}")
    evidence_hash: Mapped[str] = mapped_column(String(80), index=True)
    extraction_method: Mapped[str] = mapped_column(String(80), default="demo_seed")
    source_version: Mapped[int] = mapped_column(Integer, default=1)
    language: Mapped[str] = mapped_column(String(16), default="en")
    quality_score: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    source: Mapped[Source] = relationship(back_populates="evidence_items")
    claim_links: Mapped[list["ClaimEvidence"]] = relationship(back_populates="evidence", cascade="all, delete-orphan")


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("task_id", "subject", "predicate", "claim_type", name="uq_claim_task_fact"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("claim"))
    task_id: Mapped[str] = mapped_column(ForeignKey("research_tasks.id"), index=True)
    subject: Mapped[str] = mapped_column(String(160), index=True)
    predicate: Mapped[str] = mapped_column(String(120), index=True)
    value_json: Mapped[str] = mapped_column(Text, default="{}")
    claim_type: Mapped[str] = mapped_column(String(80), index=True)
    dimension: Mapped[str] = mapped_column(String(120), default="general", index=True)
    status: Mapped[str] = mapped_column(String(40), default=ClaimStatus.needs_evidence.value, index=True)
    confidence: Mapped[str] = mapped_column(String(40), default="medium")
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5)
    display_text: Mapped[str] = mapped_column(Text)
    include_in_report: Mapped[bool] = mapped_column(default=True)
    evidence_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    task: Mapped[ResearchTask] = relationship(back_populates="claims")
    evidence_links: Mapped[list["ClaimEvidence"]] = relationship(back_populates="claim", cascade="all, delete-orphan")
    review_decisions: Mapped[list["ReviewDecision"]] = relationship(back_populates="claim", cascade="all, delete-orphan")


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    __table_args__ = (
        UniqueConstraint("claim_id", "evidence_id", "relation", name="uq_claim_evidence_relation"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("ce"))
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), index=True)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"), index=True)
    relation: Mapped[str] = mapped_column(String(40), default="supports")
    weight: Mapped[float] = mapped_column(Float, default=1.0)

    claim: Mapped[Claim] = relationship(back_populates="evidence_links")
    evidence: Mapped[Evidence] = relationship(back_populates="claim_links")


class ReviewDecision(Base):
    __tablename__ = "review_decisions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("review"))
    claim_id: Mapped[str] = mapped_column(ForeignKey("claims.id"), index=True)
    decision: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    previous_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    resulting_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reviewed_by: Mapped[str] = mapped_column(String(80), default="local-user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    claim: Mapped[Claim] = relationship(back_populates="review_decisions")


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("task_id", "version", name="uq_report_task_version"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("report"))
    task_id: Mapped[str] = mapped_column(ForeignKey("research_tasks.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(40), default="draft")
    citation_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    input_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    task: Mapped[ResearchTask] = relationship(back_populates="reports")
    sections: Mapped[list["ReportSection"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    artifacts: Mapped[list["ReportArtifact"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class ReportSection(Base):
    __tablename__ = "report_sections"
    __table_args__ = (
        UniqueConstraint("report_id", "order_no", name="uq_report_section_order"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("section"))
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    section_type: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(160))
    content_markdown: Mapped[str] = mapped_column(Text)
    order_no: Mapped[int] = mapped_column(Integer)

    report: Mapped[Report] = relationship(back_populates="sections")


class ReportArtifact(Base):
    __tablename__ = "report_artifacts"
    __table_args__ = (
        UniqueConstraint("report_id", "artifact_type", name="uq_report_artifact_type"),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("rart"))
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(40))
    object_key: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(80))
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    report: Mapped[Report] = relationship(back_populates="artifacts")


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("upload"))
    organization_id: Mapped[str] = mapped_column(String(40), index=True)
    object_key: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    parse_status: Mapped[str] = mapped_column(String(40), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
