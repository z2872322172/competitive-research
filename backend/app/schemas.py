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
    clarification_answers: list[dict[str, Any]] = Field(default_factory=list)
    research_weights: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class ResearchClarifyRequest(BaseModel):
    prompt: str = Field(min_length=8)
    workspace_id: str = "default"


class ClarificationQuestionOut(BaseModel):
    key: str
    label: str
    question: str
    reason: str = ""
    answer_type: Literal["free_text", "single_choice", "multi_choice"] = "free_text"
    options: list[str] = Field(default_factory=list)
    required: bool = False


class ResearchPlanSuggestionOut(BaseModel):
    research_question: str
    detected_domain: str
    detected_intent: str
    research_type: Literal["competitive_research", "deep_research"]
    competitors: list[str]
    dimensions: list[str]
    source_preferences: list[str]
    time_range: str
    report_depth: str
    output_format: str
    questions: list[ClarificationQuestionOut]
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResearchTaskOut(BaseModel):
    id: int
    title: str
    prompt: str
    scope: dict[str, Any]
    status: str
    workspace_id: str
    current_run_id: int | None
    failure_reason: str | None
    created_by: str
    confirmed_at: datetime | None
    queued_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskRunOut(BaseModel):
    id: int
    task_id: int
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
    id: int
    run_id: int
    sequence_no: int
    type: str
    stage: str
    message: str
    payload: dict[str, Any]
    severity: str
    actor: str
    created_at: datetime


class SourceReliabilityOut(BaseModel):
    score: float
    label: Literal["high", "medium", "low"]
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SourceOut(BaseModel):
    id: int
    task_id: int
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
    reliability: SourceReliabilityOut | None = None

    model_config = {"from_attributes": True}


class SourceSnapshotOut(BaseModel):
    source_id: int
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


class AuthRegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=80)
    # 注册时加入的工作区；不传则默认分配 "{username}-default" 个人工作区（首个成员为 owner）。
    workspace_id: str | None = Field(default=None, max_length=40)


class AuthLoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


class WorkspaceMembershipOut(BaseModel):
    workspace_id: str
    role: str


class AuthUserOut(BaseModel):
    id: int
    username: str
    display_name: str
    is_active: bool
    workspaces: list[WorkspaceMembershipOut]


class AuthTokenOut(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthUserOut


class CompetitorProfileCreate(BaseModel):
    name: str = Field(min_length=1)
    category: str = "general"
    description: str = ""
    homepage_url: str = ""
    source_urls: list[CompetitorSourceUrl] = Field(default_factory=list)
    workspace_id: str = "default"


class CompetitorProfileOut(BaseModel):
    id: int
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
    id: int
    source_id: int
    quote: str
    locator: dict[str, Any]
    social_metadata: dict[str, Any] = Field(default_factory=dict)
    evidence_hash: str
    extraction_method: str
    source_version: int
    language: str
    quality_score: float
    source: SourceOut | None = None


class ClaimEvidenceLinkOut(BaseModel):
    evidence_id: int
    relation: str
    weight: float


class ClaimConflictAnalysisOut(BaseModel):
    support_count: int
    conflict_count: int
    context_count: int
    support_score: float
    conflict_score: float
    preferred_relation: str
    needs_more_research: bool
    recommendation: str
    rationale: list[str] = Field(default_factory=list)
    distinct_source_count: int = 0
    source_diversity_score: float = 0.0
    max_supporting_source_reliability: float = 0.0
    confidence_breakdown: dict[str, float] = Field(default_factory=dict)


class ClaimOut(BaseModel):
    id: int
    task_id: int
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
    evidence_ids: list[int] = Field(default_factory=list)
    evidence_links: list[ClaimEvidenceLinkOut] = Field(default_factory=list)
    conflict_analysis: ClaimConflictAnalysisOut | None = None
    review_decision: str | None = None
    review_reason: str | None = None
    reviewed_at: datetime | None = None


class ReviewDecisionCreate(BaseModel):
    decision: Literal["accept", "mark_uncertain", "exclude", "continue_research"]
    reason: str = ""


class CancelTaskCreate(BaseModel):
    reason: str = "canceled by user"


class ReviewDecisionOut(BaseModel):
    id: int
    claim_id: int
    decision: str
    reason: str
    previous_status: str | None
    resulting_status: str | None
    reviewed_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportSectionEvidenceOut(BaseModel):
    id: int
    source_id: int
    quote: str
    source_title: str | None = None
    source_url: str | None = None
    publisher: str | None = None
    source_type: str | None = None
    quality_score: float
    reliability_score: float | None = None
    reliability_level: str | None = None
    reliability_reasons: list[str] = Field(default_factory=list)
    relation: str | None = None
    locator: dict[str, Any] = Field(default_factory=dict)
    snapshot_available: bool = False
    content_hash: str | None = None
    claim_ids: list[int] = Field(default_factory=list)


class ReportSectionOut(BaseModel):
    id: int
    section_type: str
    title: str
    content_markdown: str
    order_no: int
    evidence: list[ReportSectionEvidenceOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ReportOut(BaseModel):
    id: int
    task_id: int
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
    task_id: int
    sources_indexed: int
    evidence_indexed: int
    failed_sources: int
    index_backend: str


class SearchHitOut(BaseModel):
    id: int
    kind: str
    score: float
    task_id: int
    source_id: int | None
    title: str
    snippet: str
    source_type: str | None
    publisher: str | None
    source_url: str | None
    competitors: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
