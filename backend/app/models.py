from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# 大 JSON 字段类型：SQLite 用 TEXT（无长度限制），MySQL 用 MEDIUMTEXT（16MB）。
# 背景workflow状态 JSON 可超过 MySQL TEXT 的 64KB 上限（如 state_json 存放全部证据与来源内容）。
LargeText = Text().with_variant(MEDIUMTEXT(), "mysql")

# 自增主键/外键类型：SQLite 用 INTEGER（rowid 自增语义），MySQL 用 BIGINT。
AutoId = Integer().with_variant(BigInteger(), "mysql")


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
    __table_args__ = {"comment": "研究任务主表：一次竞品调研需求对应一条记录"}

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="任务ID（自增主键）")
    title: Mapped[str] = mapped_column(String(255), comment="任务标题（由需求解析生成）")
    prompt: Mapped[str] = mapped_column(Text, comment="用户原始需求描述")
    scope_json: Mapped[str] = mapped_column(Text, default="{}", comment="结构化研究范围 JSON：竞品/维度/检索策略等")
    status: Mapped[str] = mapped_column(String(40), default=TaskStatus.draft.value, index=True, comment="任务状态：draft/confirmed/queued/running/waiting_review/completed/failed/canceled")
    workspace_id: Mapped[str] = mapped_column(String(40), default="default", index=True, comment="工作空间ID（数据隔离边界）")
    current_run_id: Mapped[int | None] = mapped_column(AutoId, nullable=True, index=True, comment="当前执行批次ID，指向 task_runs.id")
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="任务失败原因（失败时填写）")
    created_by: Mapped[str] = mapped_column(String(80), default="local-user", comment="创建人标识")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="用户确认时间")
    queued_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="进入执行队列时间")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="任务完成时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, comment="更新时间")

    runs: Mapped[list["TaskRun"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    sources: Mapped[list["Source"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    claims: Mapped[list["Claim"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship(back_populates="task", cascade="all, delete-orphan")


class CompetitorProfile(Base):
    __tablename__ = "competitor_profiles"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_competitor_profile_workspace_name"),
        {"comment": "竞品档案库：工作空间内维护的竞品基础信息"},
    )

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="竞品档案ID（自增主键）")
    workspace_id: Mapped[str] = mapped_column(String(40), default="default", index=True, comment="工作空间ID（同一空间内竞品名唯一）")
    name: Mapped[str] = mapped_column(String(160), index=True, comment="竞品名称")
    category: Mapped[str] = mapped_column(String(120), default="general", comment="竞品分类，如 general/ai_ide/dev_tool")
    description: Mapped[str] = mapped_column(Text, default="", comment="竞品描述")
    homepage_url: Mapped[str] = mapped_column(String(2048), default="", comment="官网地址")
    source_urls_json: Mapped[str] = mapped_column(Text, default="[]", comment="常用信息源 URL 列表 JSON")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, comment="更新时间")


class TaskRun(Base):
    __tablename__ = "task_runs"
    __table_args__ = {"comment": "任务执行批次：任务每次启动/重试产生一条运行记录"}

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="运行批次ID（自增主键）")
    task_id: Mapped[int] = mapped_column(AutoId, ForeignKey("research_tasks.id"), index=True, comment="所属任务ID")
    status: Mapped[str] = mapped_column(String(40), default=RunStatus.queued.value, index=True, comment="运行状态：queued/running/waiting_review/completed/failed/canceled")
    current_stage: Mapped[str] = mapped_column(String(80), default="queued", comment="当前执行到的阶段/节点名")
    iteration_count: Mapped[int] = mapped_column(Integer, default=0, comment="迭代轮次（补充检索用）")
    priority: Mapped[int] = mapped_column(Integer, default=5, comment="执行优先级，数值越小越先执行")
    input_snapshot_json: Mapped[str] = mapped_column(LargeText, default="{}", comment="本次运行输入快照 JSON（含 scope 等）")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="运行失败错误信息")
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, comment="入队时间")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始执行时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="结束时间（成功或失败）")

    task: Mapped[ResearchTask] = relationship(back_populates="runs")
    events: Mapped[list["ResearchEvent"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    checkpoints: Mapped[list["WorkflowCheckpoint"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class ResearchEvent(Base):
    __tablename__ = "research_events"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence_no", name="uq_run_sequence"),
        {"comment": "研究过程事件流：节点进度与业务事件，前端时间线的数据源"},
    )

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="事件ID（自增主键）")
    run_id: Mapped[int] = mapped_column(AutoId, ForeignKey("task_runs.id"), index=True, comment="所属运行批次ID")
    sequence_no: Mapped[int] = mapped_column(Integer, comment="事件序号（同一运行内严格递增）")
    type: Mapped[str] = mapped_column(String(80), index=True, comment="事件类型：node.started/search.started/evidence.created 等")
    stage: Mapped[str] = mapped_column(String(80), comment="事件所属阶段/节点名")
    message: Mapped[str] = mapped_column(Text, comment="事件可读消息")
    payload_json: Mapped[str] = mapped_column(LargeText, default="{}", comment="事件负载数据 JSON")
    severity: Mapped[str] = mapped_column(String(20), default="info", index=True, comment="严重级别：info/warning/error")
    actor: Mapped[str] = mapped_column(String(80), default="system", comment="产生者：system/llm/human 等")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, comment="创建时间")

    run: Mapped[TaskRun] = relationship(back_populates="events")


class WorkflowCheckpoint(Base):
    __tablename__ = "workflow_checkpoints"
    __table_args__ = (
        UniqueConstraint("run_id", "sequence_no", name="uq_workflow_checkpoint_sequence"),
        {"comment": "工作流检查点：记录每个节点完成状态，用于失败后断点恢复"},
    )

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="检查点ID（自增主键）")
    run_id: Mapped[int] = mapped_column(AutoId, ForeignKey("task_runs.id"), index=True, comment="所属运行批次ID")
    sequence_no: Mapped[int] = mapped_column(Integer, comment="检查点序号（同一运行内递增）")
    node_name: Mapped[str] = mapped_column(String(80), index=True, comment="节点名，如 search/fetch/extract")
    resume_node: Mapped[str] = mapped_column(String(80), index=True, comment="恢复执行时的起始节点（可与 node_name 不同）")
    status: Mapped[str] = mapped_column(String(40), default="succeeded", index=True, comment="节点执行状态")
    input_summary_json: Mapped[str] = mapped_column(LargeText, default="{}", comment="节点输入摘要 JSON")
    output_summary_json: Mapped[str] = mapped_column(LargeText, default="{}", comment="节点输出摘要 JSON")
    state_json: Mapped[str] = mapped_column(LargeText, default="{}", comment="恢复所需的工作流状态 JSON")
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True, comment="节点失败错误摘要")
    retry_count: Mapped[int] = mapped_column(Integer, default=0, comment="重试次数")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, comment="创建时间")

    run: Mapped[TaskRun] = relationship(back_populates="checkpoints")


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("task_id", "content_hash", name="uq_source_task_content_hash"),
        {"comment": "信息来源表：研究过程中采集到的网页/文档等来源（任务内按内容哈希去重）"},
    )

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="来源ID（自增主键）")
    task_id: Mapped[int] = mapped_column(AutoId, ForeignKey("research_tasks.id"), index=True, comment="所属任务ID")
    url: Mapped[str] = mapped_column(String(2048), comment="原始抓取 URL")
    canonical_url: Mapped[str] = mapped_column(String(2048), comment="规范化 URL（去跟踪参数等）")
    source_type: Mapped[str] = mapped_column(String(40), index=True, comment="来源类型：web/doc/pdf/social/manual 等")
    title: Mapped[str] = mapped_column(String(255), comment="来源标题")
    publisher: Mapped[str] = mapped_column(String(120), comment="发布方/站点名")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="内容发布时间")
    social_platform: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True, comment="社交平台名（社交来源专用）")
    sentiment: Mapped[str | None] = mapped_column(String(40), nullable=True, comment="情感倾向：positive/neutral/negative")
    heat_score: Mapped[float | None] = mapped_column(Float, nullable=True, comment="热度分（社交来源专用）")
    interaction_metrics_json: Mapped[str] = mapped_column(Text, default="{}", comment="互动指标 JSON：点赞/评论/转发数等")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, comment="抓取时间")
    content_hash: Mapped[str] = mapped_column(String(80), index=True, comment="内容哈希（任务内去重依据）")
    index_status: Mapped[str] = mapped_column(String(40), default="pending", comment="ES 索引状态：pending/indexed/failed/skipped")
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="索引完成时间")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否一手来源（区别于转载/评论）")

    task: Mapped[ResearchTask] = relationship(back_populates="sources")
    evidence_items: Mapped[list["Evidence"]] = relationship(back_populates="source", cascade="all, delete-orphan")
    artifacts: Mapped[list["SourceArtifact"]] = relationship(back_populates="source", cascade="all, delete-orphan")


class SourceArtifact(Base):
    __tablename__ = "source_artifacts"
    __table_args__ = (
        UniqueConstraint("source_id", "artifact_type", name="uq_source_artifact_type"),
        {"comment": "来源原始工件表：来源的 HTML 快照等原始文件在 ArtifactStorage 中的定位记录"},
    )

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="工件ID（自增主键）")
    source_id: Mapped[int] = mapped_column(AutoId, ForeignKey("sources.id"), index=True, comment="所属来源ID")
    artifact_type: Mapped[str] = mapped_column(String(40), comment="工件类型：snapshot/original 等")
    object_key: Mapped[str] = mapped_column(Text, comment="ArtifactStorage 对象键，如 snapshots/{task_id}/{source_id}.html")
    sha256: Mapped[str] = mapped_column(String(80), comment="文件内容 SHA256（完整性校验/去重锚点）")
    content_type: Mapped[str] = mapped_column(String(120), default="text/html; charset=utf-8", comment="文件 MIME 类型")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, comment="文件大小（字节）")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, comment="创建时间")

    source: Mapped[Source] = relationship(back_populates="artifacts")


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        UniqueConstraint("source_id", "evidence_hash", name="uq_evidence_source_hash"),
        {"comment": "证据表：从来源中抽取的带引文证据片段（来源内按哈希去重）"},
    )

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="证据ID（自增主键）")
    source_id: Mapped[int] = mapped_column(AutoId, ForeignKey("sources.id"), index=True, comment="所属来源ID")
    quote: Mapped[str] = mapped_column(Text, comment="原文引文（证据核心内容）")
    locator_json: Mapped[str] = mapped_column(Text, default="{}", comment="引文定位 JSON：标题/字符区间/锚点等")
    evidence_hash: Mapped[str] = mapped_column(String(80), index=True, comment="证据内容哈希（去重依据）")
    extraction_method: Mapped[str] = mapped_column(String(80), default="demo_seed", comment="抽取方式：llm/rule_based/demo_seed")
    source_version: Mapped[int] = mapped_column(Integer, default=1, comment="来源内容版本号")
    language: Mapped[str] = mapped_column(String(16), default="en", comment="证据语言：en/zh 等")
    quality_score: Mapped[float] = mapped_column(Float, default=0.5, comment="证据质量分 0-1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, comment="创建时间")

    source: Mapped[Source] = relationship(back_populates="evidence_items")
    claim_links: Mapped[list["ClaimEvidence"]] = relationship(back_populates="evidence", cascade="all, delete-orphan")


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        UniqueConstraint("task_id", "subject", "predicate", "claim_type", name="uq_claim_task_fact"),
        {"comment": "结论表：从证据归纳出的事实主张（任务内按主谓类型三元组去重）"},
    )

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="结论ID（自增主键）")
    task_id: Mapped[int] = mapped_column(AutoId, ForeignKey("research_tasks.id"), index=True, comment="所属任务ID")
    subject: Mapped[str] = mapped_column(String(160), index=True, comment="结论主语（通常是竞品名）")
    predicate: Mapped[str] = mapped_column(String(120), index=True, comment="结论谓语（属性/维度，如 enterprise_pricing）")
    value_json: Mapped[str] = mapped_column(Text, default="{}", comment="结论值 JSON")
    claim_type: Mapped[str] = mapped_column(String(80), index=True, comment="结论类型：pricing/feature/integration/risk 等")
    dimension: Mapped[str] = mapped_column(String(120), default="general", index=True, comment="所属研究维度")
    status: Mapped[str] = mapped_column(String(40), default=ClaimStatus.needs_evidence.value, index=True, comment="审核状态：verified/low_confidence/conflict/undisclosed/needs_evidence")
    confidence: Mapped[str] = mapped_column(String(40), default="medium", comment="置信级别：high/medium/low")
    confidence_score: Mapped[float] = mapped_column(Float, default=0.5, comment="置信分 0-1")
    display_text: Mapped[str] = mapped_column(Text, comment="结论展示文本（报告引用用）")
    include_in_report: Mapped[bool] = mapped_column(default=True, comment="是否纳入报告（人工排除后为 false）")
    evidence_coverage: Mapped[float] = mapped_column(Float, default=0.0, comment="证据覆盖率 0-1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, comment="创建时间")

    task: Mapped[ResearchTask] = relationship(back_populates="claims")
    evidence_links: Mapped[list["ClaimEvidence"]] = relationship(back_populates="claim", cascade="all, delete-orphan")
    review_decisions: Mapped[list["ReviewDecision"]] = relationship(back_populates="claim", cascade="all, delete-orphan")


class ClaimEvidence(Base):
    __tablename__ = "claim_evidence"
    __table_args__ = (
        UniqueConstraint("claim_id", "evidence_id", "relation", name="uq_claim_evidence_relation"),
        {"comment": "结论-证据关联表：Claim 必须绑定 Evidence 的落地（证据链核心约束）"},
    )

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="关联ID（自增主键）")
    claim_id: Mapped[int] = mapped_column(AutoId, ForeignKey("claims.id"), index=True, comment="结论ID")
    evidence_id: Mapped[int] = mapped_column(AutoId, ForeignKey("evidence.id"), index=True, comment="证据ID")
    relation: Mapped[str] = mapped_column(String(40), default="supports", comment="关联关系：supports/conflicts")
    weight: Mapped[float] = mapped_column(Float, default=1.0, comment="关联权重（影响覆盖度计算）")

    claim: Mapped[Claim] = relationship(back_populates="evidence_links")
    evidence: Mapped[Evidence] = relationship(back_populates="claim_links")


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    __table_args__ = {"comment": "人工审核决策表：对风险 Claim 的每次审核动作留痕"}

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="决策ID（自增主键）")
    claim_id: Mapped[int] = mapped_column(AutoId, ForeignKey("claims.id"), index=True, comment="被审核的结论ID")
    decision: Mapped[str] = mapped_column(String(40), comment="审核动作：accept/reject/mark_uncertain")
    reason: Mapped[str] = mapped_column(Text, comment="审核理由（必填）")
    previous_status: Mapped[str | None] = mapped_column(String(40), nullable=True, comment="审核前状态")
    resulting_status: Mapped[str | None] = mapped_column(String(40), nullable=True, comment="审核后状态")
    reviewed_by: Mapped[str] = mapped_column(String(80), default="local-user", comment="审核人标识")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, comment="审核时间")

    claim: Mapped[Claim] = relationship(back_populates="review_decisions")


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("task_id", "version", name="uq_report_task_version"),
        {"comment": "报告表：任务研究报告（版本化，审核后重生成产生新版本）"},
    )

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="报告ID（自增主键）")
    task_id: Mapped[int] = mapped_column(AutoId, ForeignKey("research_tasks.id"), index=True, comment="所属任务ID")
    version: Mapped[int] = mapped_column(Integer, default=1, comment="报告版本号（任务内递增）")
    status: Mapped[str] = mapped_column(String(40), default="draft", comment="报告状态：draft/generated/export_failed")
    citation_coverage: Mapped[float] = mapped_column(Float, default=0.0, comment="引用覆盖率 0-1（结论引用证据比例）")
    input_snapshot_json: Mapped[str] = mapped_column(LargeText, default="{}", comment="生成时输入快照 JSON（含纳入的 Claim 集合）")
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="生成完成时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, comment="创建时间")

    task: Mapped[ResearchTask] = relationship(back_populates="reports")
    sections: Mapped[list["ReportSection"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    artifacts: Mapped[list["ReportArtifact"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class ReportSection(Base):
    __tablename__ = "report_sections"
    __table_args__ = (
        UniqueConstraint("report_id", "order_no", name="uq_report_section_order"),
        {"comment": "报告章节表：报告正文的分章节内容"},
    )

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="章节ID（自增主键）")
    report_id: Mapped[int] = mapped_column(AutoId, ForeignKey("reports.id"), index=True, comment="所属报告ID")
    section_type: Mapped[str] = mapped_column(String(80), comment="章节类型：summary/key_findings/risks/appendix 等")
    title: Mapped[str] = mapped_column(String(160), comment="章节标题")
    content_markdown: Mapped[str] = mapped_column(Text, comment="章节正文（Markdown，含证据引用标记）")
    order_no: Mapped[int] = mapped_column(Integer, comment="章节排序号")

    report: Mapped[Report] = relationship(back_populates="sections")


class ReportArtifact(Base):
    __tablename__ = "report_artifacts"
    __table_args__ = (
        UniqueConstraint("report_id", "artifact_type", name="uq_report_artifact_type"),
        {"comment": "报告导出工件表：导出的 markdown/pdf/docx 文件在 ArtifactStorage 中的定位记录"},
    )

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="工件ID（自增主键）")
    report_id: Mapped[int] = mapped_column(AutoId, ForeignKey("reports.id"), index=True, comment="所属报告ID")
    artifact_type: Mapped[str] = mapped_column(String(40), comment="导出格式：markdown/pdf/docx")
    object_key: Mapped[str] = mapped_column(Text, comment="ArtifactStorage 对象键，如 reports/{task_id}/v{n}/report.md")
    sha256: Mapped[str] = mapped_column(String(80), comment="文件内容 SHA256（完整性校验）")
    content_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream", comment="文件 MIME 类型")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, comment="文件大小（字节）")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, comment="创建时间")

    report: Mapped[Report] = relationship(back_populates="artifacts")


class Upload(Base):
    __tablename__ = "uploads"
    __table_args__ = {"comment": "用户上传文件表：研究时上传的补充资料在 ArtifactStorage 中的记录"}

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="上传ID（自增主键）")
    organization_id: Mapped[str] = mapped_column(String(40), index=True, comment="所属组织/工作空间ID")
    object_key: Mapped[str] = mapped_column(Text, comment="ArtifactStorage 对象键，如 uploads/{org}/{upload_id}/{filename}")
    filename: Mapped[str] = mapped_column(String(255), comment="原始文件名")
    mime_type: Mapped[str] = mapped_column(String(120), comment="文件 MIME 类型")
    parse_status: Mapped[str] = mapped_column(String(40), default="pending", comment="解析状态：pending/parsed/failed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, comment="上传时间")


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"comment": "用户表：登录态主体，密码使用 PBKDF2 哈希存储"}

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="用户ID（自增主键）")
    username: Mapped[str] = mapped_column(String(80), unique=True, comment="登录用户名（全局唯一）")
    password_hash: Mapped[str] = mapped_column(String(255), comment="PBKDF2-SHA256 密码哈希，格式 pbkdf2_sha256$迭代$盐$哈希")
    display_name: Mapped[str] = mapped_column(String(80), default="", comment="显示名（可选）")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否启用（禁用后令牌立即失效）")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, comment="更新时间")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
        {"comment": "工作空间成员表：用户与工作区的多对多关系，鉴权隔离的成员边界"},
    )

    id: Mapped[int] = mapped_column(AutoId, primary_key=True, autoincrement=True, comment="成员关系ID（自增主键）")
    workspace_id: Mapped[str] = mapped_column(String(40), index=True, comment="工作空间ID")
    user_id: Mapped[int] = mapped_column(AutoId, ForeignKey("users.id"), index=True, comment="用户ID，指向 users.id")
    role: Mapped[str] = mapped_column(String(20), default="member", comment="成员角色：owner/member")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, comment="加入时间")


# MySQL 统一表选项：InnoDB 引擎 + utf8mb4 字符集（中文注释/内容安全）。
# SQLite 等其他方言会忽略 mysql_* 选项，不影响测试。
for _table in Base.metadata.tables.values():
    _table.kwargs.setdefault("mysql_engine", "InnoDB")
    _table.kwargs.setdefault("mysql_charset", "utf8mb4")
    _table.kwargs.setdefault("mysql_collate", "utf8mb4_unicode_ci")
