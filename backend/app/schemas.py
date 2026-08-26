from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ResearchTaskCreate(BaseModel):
    prompt: str = Field(min_length=8)
    title: str | None = None
    research_type: Literal["competitive_research", "deep_research"] | None = None
    template: str | None = None
    research_question: str | None = None
    research_aspects: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    source_preferences: list[str] = Field(default_factory=list)
    workspace_id: str = "default"
    created_by: str = "local-user"
    report_depth: str = "standard"
    time_range: str = "last_12_months"
    output_format: str = "comprehensive_report"


class ResearchTaskOut(BaseModel):
    id: str
    title: str
    prompt: str
    scope: dict[str, Any]
    status: str
    workspace_id: str
    current_run_id: str | None
    failure_reason: str | None
    created_by: str
    confirmed_at: datetime | None
    queued_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskRunOut(BaseModel):
    id: str
    task_id: str
    status: str
    current_stage: str
    iteration_count: int
    priority: int
    input_snapshot: dict[str, Any]
    error_message: str | None
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class ResearchEventOut(BaseModel):
    id: str
    run_id: str
    sequence_no: int
    type: str
    stage: str
    message: str
    payload: dict[str, Any]
    severity: str
    actor: str
    created_at: datetime


class SourceOut(BaseModel):
    id: str
    task_id: str
    url: str
    canonical_url: str
    source_type: str
    title: str
    publisher: str
    published_at: datetime | None
    social_platform: str | None = None
    sentiment: str | None = None
    heat_score: float | None = None
    interaction_metrics: dict[str, Any] = Field(default_factory=dict)
    retrieved_at: datetime
    content_hash: str
    index_status: str
    is_primary: bool

    model_config = {"from_attributes": True}


class SourceSnapshotOut(BaseModel):
    source_id: str
    artifact_type: str
    available: bool
    content_hash: str | None
    object_key: str | None
    summary: str
    char_count: int


class CompetitorSourceUrl(BaseModel):
    label: str
    url: str
    source_type: str = "official"


class CompetitorProfileCreate(BaseModel):
    name: str = Field(min_length=1)
    category: str = "general"
    description: str = ""
    homepage_url: str = ""
    source_urls: list[CompetitorSourceUrl] = Field(default_factory=list)
    workspace_id: str = "default"


class CompetitorProfileOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    category: str
    description: str
    homepage_url: str
    source_urls: list[CompetitorSourceUrl]
    source_count: int
    task_count: int
    verified_claim_count: int
    risky_claim_count: int
    report_count: int
    created_at: datetime
    updated_at: datetime


class EvidenceOut(BaseModel):
    id: str
    source_id: str
    quote: str
    locator: dict[str, Any]
    social_metadata: dict[str, Any] = Field(default_factory=dict)
    evidence_hash: str
    extraction_method: str
    source_version: int
    language: str
    quality_score: float
    source: SourceOut | None = None


class ClaimOut(BaseModel):
    id: str
    task_id: str
    subject: str
    predicate: str
    value: dict[str, Any]
    claim_type: str
    dimension: str
    status: str
    confidence: str
    confidence_score: float
    display_text: str
    include_in_report: bool
    evidence_coverage: float
    evidence_ids: list[str] = Field(default_factory=list)
    review_decision: str | None = None
    review_reason: str | None = None
    reviewed_at: datetime | None = None


class ReviewDecisionCreate(BaseModel):
    decision: Literal["accept", "mark_uncertain", "exclude", "continue_research"]
    reason: str = ""


class CancelTaskCreate(BaseModel):
    reason: str = "canceled by user"


class ReviewDecisionOut(BaseModel):
    id: str
    claim_id: str
    decision: str
    reason: str
    previous_status: str | None
    resulting_status: str | None
    reviewed_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportSectionEvidenceOut(BaseModel):
    id: str
    source_id: str
    quote: str
    source_title: str | None = None
    source_url: str | None = None
    publisher: str | None = None
    quality_score: float
    relation: str | None = None
    claim_ids: list[str] = Field(default_factory=list)


class ReportSectionOut(BaseModel):
    id: str
    section_type: str
    title: str
    content_markdown: str
    order_no: int
    evidence: list[ReportSectionEvidenceOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ReportOut(BaseModel):
    id: str
    task_id: str
    version: int
    status: str
    citation_coverage: float
    input_snapshot: dict[str, Any]
    generated_at: datetime | None
    created_at: datetime
    sections: list[ReportSectionOut]

    model_config = {"from_attributes": True}


class TaskDetailOut(BaseModel):
    task: ResearchTaskOut
    latest_run: TaskRunOut | None
    runs: list[TaskRunOut] = Field(default_factory=list)
    sources: list[SourceOut]
    evidence: list[EvidenceOut]
    claims: list[ClaimOut]
    reports: list[ReportOut]


class MonitoringMetricCounts(BaseModel):
    research_tasks: int
    task_runs: int
    research_events: int
    sources: int
    evidence: int
    claims: int
    reports: int
    review_decisions: int
    source_artifacts: int


class MonitoringMetricsOut(BaseModel):
    environment: str
    task_mode: str
    database_backend: str
    counts: MonitoringMetricCounts
    latest_run_started_at: datetime | None = None
    latest_run_finished_at: datetime | None = None
    latest_event_at: datetime | None = None


class SearchIndexRebuildOut(BaseModel):
    task_id: str
    sources_indexed: int
    evidence_indexed: int
    failed_sources: int
    index_backend: str


class SearchHitOut(BaseModel):
    id: str
    kind: str
    score: float
    task_id: str
    source_id: str | None
    title: str
    snippet: str
    source_type: str | None
    publisher: str | None
    source_url: str | None
    competitors: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
