-- =============================================================
-- 智能竞品分析 Agent - MySQL 初始化建表脚本
-- 由 scripts/generate_mysql_schema.py 从 app/models.py 自动生成，请勿手改。
-- 主键统一为 BIGINT 自增；业务 ID（如 task_xxx）暂不引入，后续如需再加独立列。
-- 执行方式（任选其一）：
--   1) mysql -u root -p < scripts/init_mysql_schema.sql
--   2) 在 MySQL 客户端中选中目标库后直接执行本文件
-- 注意：本脚本会先 DROP 再 CREATE，会清空库中既有数据，请确认后执行。
-- =============================================================

CREATE DATABASE IF NOT EXISTS `verda` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `verda`;

-- 先关外键检查再删表，避免表间依赖导致删除失败
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS claim_evidence;
DROP TABLE IF EXISTS workflow_checkpoints;
DROP TABLE IF EXISTS source_artifacts;
DROP TABLE IF EXISTS review_decisions;
DROP TABLE IF EXISTS research_events;
DROP TABLE IF EXISTS report_sections;
DROP TABLE IF EXISTS report_artifacts;
DROP TABLE IF EXISTS evidence;
DROP TABLE IF EXISTS workspace_members;
DROP TABLE IF EXISTS task_runs;
DROP TABLE IF EXISTS sources;
DROP TABLE IF EXISTS reports;
DROP TABLE IF EXISTS claims;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS uploads;
DROP TABLE IF EXISTS research_tasks;
DROP TABLE IF EXISTS competitor_profiles;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE competitor_profiles (
	id BIGINT NOT NULL COMMENT '竞品档案ID（自增主键）' AUTO_INCREMENT, 
	workspace_id VARCHAR(40) NOT NULL COMMENT '工作空间ID（同一空间内竞品名唯一）', 
	name VARCHAR(160) NOT NULL COMMENT '竞品名称', 
	category VARCHAR(120) NOT NULL COMMENT '竞品分类，如 general/ai_ide/dev_tool', 
	description TEXT NOT NULL COMMENT '竞品描述', 
	homepage_url VARCHAR(2048) NOT NULL COMMENT '官网地址', 
	source_urls_json TEXT NOT NULL COMMENT '常用信息源 URL 列表 JSON', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_competitor_profile_workspace_name UNIQUE (workspace_id, name)
)COMMENT='竞品档案库：工作空间内维护的竞品基础信息' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE INDEX ix_competitor_profiles_name ON competitor_profiles (name);
CREATE INDEX ix_competitor_profiles_workspace_id ON competitor_profiles (workspace_id);

CREATE TABLE research_tasks (
	id BIGINT NOT NULL COMMENT '任务ID（自增主键）' AUTO_INCREMENT, 
	title VARCHAR(255) NOT NULL COMMENT '任务标题（由需求解析生成）', 
	prompt TEXT NOT NULL COMMENT '用户原始需求描述', 
	scope_json TEXT NOT NULL COMMENT '结构化研究范围 JSON：竞品/维度/检索策略等', 
	status VARCHAR(40) NOT NULL COMMENT '任务状态：draft/confirmed/queued/running/waiting_review/completed/failed/canceled', 
	workspace_id VARCHAR(40) NOT NULL COMMENT '工作空间ID（数据隔离边界）', 
	current_run_id BIGINT COMMENT '当前执行批次ID，指向 task_runs.id', 
	failure_reason TEXT COMMENT '任务失败原因（失败时填写）', 
	created_by VARCHAR(80) NOT NULL COMMENT '创建人标识', 
	confirmed_at DATETIME COMMENT '用户确认时间', 
	queued_at DATETIME COMMENT '进入执行队列时间', 
	completed_at DATETIME COMMENT '任务完成时间', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id)
)COMMENT='研究任务主表：一次竞品调研需求对应一条记录' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE INDEX ix_research_tasks_current_run_id ON research_tasks (current_run_id);
CREATE INDEX ix_research_tasks_status ON research_tasks (status);
CREATE INDEX ix_research_tasks_workspace_id ON research_tasks (workspace_id);

CREATE TABLE uploads (
	id BIGINT NOT NULL COMMENT '上传ID（自增主键）' AUTO_INCREMENT, 
	organization_id VARCHAR(40) NOT NULL COMMENT '所属组织/工作空间ID', 
	object_key TEXT NOT NULL COMMENT 'ArtifactStorage 对象键，如 uploads/{org}/{upload_id}/{filename}', 
	filename VARCHAR(255) NOT NULL COMMENT '原始文件名', 
	mime_type VARCHAR(120) NOT NULL COMMENT '文件 MIME 类型', 
	parse_status VARCHAR(40) NOT NULL COMMENT '解析状态：pending/parsed/failed', 
	created_at DATETIME NOT NULL COMMENT '上传时间', 
	PRIMARY KEY (id)
)COMMENT='用户上传文件表：研究时上传的补充资料在 ArtifactStorage 中的记录' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE INDEX ix_uploads_organization_id ON uploads (organization_id);

CREATE TABLE users (
	id BIGINT NOT NULL COMMENT '用户ID（自增主键）' AUTO_INCREMENT, 
	username VARCHAR(80) NOT NULL COMMENT '登录用户名（全局唯一）', 
	password_hash VARCHAR(255) NOT NULL COMMENT 'PBKDF2-SHA256 密码哈希，格式 pbkdf2_sha256$迭代$盐$哈希', 
	display_name VARCHAR(80) NOT NULL COMMENT '显示名（可选）', 
	is_active BOOL NOT NULL COMMENT '是否启用（禁用后令牌立即失效）', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	updated_at DATETIME NOT NULL COMMENT '更新时间', 
	PRIMARY KEY (id), 
	UNIQUE (username)
)COMMENT='用户表：登录态主体，密码使用 PBKDF2 哈希存储' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE claims (
	id BIGINT NOT NULL COMMENT '结论ID（自增主键）' AUTO_INCREMENT, 
	task_id BIGINT NOT NULL COMMENT '所属任务ID', 
	subject VARCHAR(160) NOT NULL COMMENT '结论主语（通常是竞品名）', 
	predicate VARCHAR(120) NOT NULL COMMENT '结论谓语（属性/维度，如 enterprise_pricing）', 
	value_json TEXT NOT NULL COMMENT '结论值 JSON', 
	claim_type VARCHAR(80) NOT NULL COMMENT '结论类型：pricing/feature/integration/risk 等', 
	dimension VARCHAR(120) NOT NULL COMMENT '所属研究维度', 
	status VARCHAR(40) NOT NULL COMMENT '审核状态：verified/low_confidence/conflict/undisclosed/needs_evidence', 
	confidence VARCHAR(40) NOT NULL COMMENT '置信级别：high/medium/low', 
	confidence_score FLOAT NOT NULL COMMENT '置信分 0-1', 
	display_text TEXT NOT NULL COMMENT '结论展示文本（报告引用用）', 
	include_in_report BOOL NOT NULL COMMENT '是否纳入报告（人工排除后为 false）', 
	evidence_coverage FLOAT NOT NULL COMMENT '证据覆盖率 0-1', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_claim_task_fact UNIQUE (task_id, subject, predicate, claim_type), 
	FOREIGN KEY(task_id) REFERENCES research_tasks (id)
)COMMENT='结论表：从证据归纳出的事实主张（任务内按主谓类型三元组去重）' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE INDEX ix_claims_claim_type ON claims (claim_type);
CREATE INDEX ix_claims_dimension ON claims (dimension);
CREATE INDEX ix_claims_predicate ON claims (predicate);
CREATE INDEX ix_claims_status ON claims (status);
CREATE INDEX ix_claims_subject ON claims (subject);
CREATE INDEX ix_claims_task_id ON claims (task_id);

CREATE TABLE reports (
	id BIGINT NOT NULL COMMENT '报告ID（自增主键）' AUTO_INCREMENT, 
	task_id BIGINT NOT NULL COMMENT '所属任务ID', 
	version INTEGER NOT NULL COMMENT '报告版本号（任务内递增）', 
	status VARCHAR(40) NOT NULL COMMENT '报告状态：draft/generated/export_failed', 
	citation_coverage FLOAT NOT NULL COMMENT '引用覆盖率 0-1（结论引用证据比例）', 
	input_snapshot_json MEDIUMTEXT NOT NULL COMMENT '生成时输入快照 JSON（含纳入的 Claim 集合）', 
	generated_at DATETIME COMMENT '生成完成时间', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_report_task_version UNIQUE (task_id, version), 
	FOREIGN KEY(task_id) REFERENCES research_tasks (id)
)COMMENT='报告表：任务研究报告（版本化，审核后重生成产生新版本）' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE INDEX ix_reports_task_id ON reports (task_id);

CREATE TABLE sources (
	id BIGINT NOT NULL COMMENT '来源ID（自增主键）' AUTO_INCREMENT, 
	task_id BIGINT NOT NULL COMMENT '所属任务ID', 
	url VARCHAR(2048) NOT NULL COMMENT '原始抓取 URL', 
	canonical_url VARCHAR(2048) NOT NULL COMMENT '规范化 URL（去跟踪参数等）', 
	source_type VARCHAR(40) NOT NULL COMMENT '来源类型：web/doc/pdf/social/manual 等', 
	title VARCHAR(255) NOT NULL COMMENT '来源标题', 
	publisher VARCHAR(120) NOT NULL COMMENT '发布方/站点名', 
	published_at DATETIME COMMENT '内容发布时间', 
	social_platform VARCHAR(40) COMMENT '社交平台名（社交来源专用）', 
	sentiment VARCHAR(40) COMMENT '情感倾向：positive/neutral/negative', 
	heat_score FLOAT COMMENT '热度分（社交来源专用）', 
	interaction_metrics_json TEXT NOT NULL COMMENT '互动指标 JSON：点赞/评论/转发数等', 
	retrieved_at DATETIME NOT NULL COMMENT '抓取时间', 
	content_hash VARCHAR(80) NOT NULL COMMENT '内容哈希（任务内去重依据）', 
	index_status VARCHAR(40) NOT NULL COMMENT 'ES 索引状态：pending/indexed/failed/skipped', 
	indexed_at DATETIME COMMENT '索引完成时间', 
	is_primary BOOL NOT NULL COMMENT '是否一手来源（区别于转载/评论）', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_source_task_content_hash UNIQUE (task_id, content_hash), 
	FOREIGN KEY(task_id) REFERENCES research_tasks (id)
)COMMENT='信息来源表：研究过程中采集到的网页/文档等来源（任务内按内容哈希去重）' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE INDEX ix_sources_content_hash ON sources (content_hash);
CREATE INDEX ix_sources_social_platform ON sources (social_platform);
CREATE INDEX ix_sources_source_type ON sources (source_type);
CREATE INDEX ix_sources_task_id ON sources (task_id);

CREATE TABLE task_runs (
	id BIGINT NOT NULL COMMENT '运行批次ID（自增主键）' AUTO_INCREMENT, 
	task_id BIGINT NOT NULL COMMENT '所属任务ID', 
	status VARCHAR(40) NOT NULL COMMENT '运行状态：queued/running/waiting_review/completed/failed/canceled', 
	current_stage VARCHAR(80) NOT NULL COMMENT '当前执行到的阶段/节点名', 
	iteration_count INTEGER NOT NULL COMMENT '迭代轮次（补充检索用）', 
	priority INTEGER NOT NULL COMMENT '执行优先级，数值越小越先执行', 
	input_snapshot_json MEDIUMTEXT NOT NULL COMMENT '本次运行输入快照 JSON（含 scope 等）', 
	error_message TEXT COMMENT '运行失败错误信息', 
	queued_at DATETIME NOT NULL COMMENT '入队时间', 
	started_at DATETIME COMMENT '开始执行时间', 
	finished_at DATETIME COMMENT '结束时间（成功或失败）', 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES research_tasks (id)
)COMMENT='任务执行批次：任务每次启动/重试产生一条运行记录' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE INDEX ix_task_runs_status ON task_runs (status);
CREATE INDEX ix_task_runs_task_id ON task_runs (task_id);

CREATE TABLE workspace_members (
	id BIGINT NOT NULL COMMENT '成员关系ID（自增主键）' AUTO_INCREMENT, 
	workspace_id VARCHAR(40) NOT NULL COMMENT '工作空间ID', 
	user_id BIGINT NOT NULL COMMENT '用户ID，指向 users.id', 
	`role` VARCHAR(20) NOT NULL COMMENT '成员角色：owner/member', 
	created_at DATETIME NOT NULL COMMENT '加入时间', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_workspace_member UNIQUE (workspace_id, user_id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
)COMMENT='工作空间成员表：用户与工作区的多对多关系，鉴权隔离的成员边界' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE INDEX ix_workspace_members_user_id ON workspace_members (user_id);
CREATE INDEX ix_workspace_members_workspace_id ON workspace_members (workspace_id);

CREATE TABLE evidence (
	id BIGINT NOT NULL COMMENT '证据ID（自增主键）' AUTO_INCREMENT, 
	source_id BIGINT NOT NULL COMMENT '所属来源ID', 
	quote TEXT NOT NULL COMMENT '原文引文（证据核心内容）', 
	locator_json TEXT NOT NULL COMMENT '引文定位 JSON：标题/字符区间/锚点等', 
	evidence_hash VARCHAR(80) NOT NULL COMMENT '证据内容哈希（去重依据）', 
	extraction_method VARCHAR(80) NOT NULL COMMENT '抽取方式：llm/rule_based/demo_seed', 
	source_version INTEGER NOT NULL COMMENT '来源内容版本号', 
	language VARCHAR(16) NOT NULL COMMENT '证据语言：en/zh 等', 
	quality_score FLOAT NOT NULL COMMENT '证据质量分 0-1', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_evidence_source_hash UNIQUE (source_id, evidence_hash), 
	FOREIGN KEY(source_id) REFERENCES sources (id)
)COMMENT='证据表：从来源中抽取的带引文证据片段（来源内按哈希去重）' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE INDEX ix_evidence_evidence_hash ON evidence (evidence_hash);
CREATE INDEX ix_evidence_source_id ON evidence (source_id);

CREATE TABLE report_artifacts (
	id BIGINT NOT NULL COMMENT '工件ID（自增主键）' AUTO_INCREMENT, 
	report_id BIGINT NOT NULL COMMENT '所属报告ID', 
	artifact_type VARCHAR(40) NOT NULL COMMENT '导出格式：markdown/pdf/docx', 
	object_key TEXT NOT NULL COMMENT 'ArtifactStorage 对象键，如 reports/{task_id}/v{n}/report.md', 
	sha256 VARCHAR(80) NOT NULL COMMENT '文件内容 SHA256（完整性校验）', 
	content_type VARCHAR(120) NOT NULL COMMENT '文件 MIME 类型', 
	size_bytes INTEGER NOT NULL COMMENT '文件大小（字节）', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_report_artifact_type UNIQUE (report_id, artifact_type), 
	FOREIGN KEY(report_id) REFERENCES reports (id)
)COMMENT='报告导出工件表：导出的 markdown/pdf/docx 文件在 ArtifactStorage 中的定位记录' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE INDEX ix_report_artifacts_report_id ON report_artifacts (report_id);

CREATE TABLE report_sections (
	id BIGINT NOT NULL COMMENT '章节ID（自增主键）' AUTO_INCREMENT, 
	report_id BIGINT NOT NULL COMMENT '所属报告ID', 
	section_type VARCHAR(80) NOT NULL COMMENT '章节类型：summary/key_findings/risks/appendix 等', 
	title VARCHAR(160) NOT NULL COMMENT '章节标题', 
	content_markdown TEXT NOT NULL COMMENT '章节正文（Markdown，含证据引用标记）', 
	order_no INTEGER NOT NULL COMMENT '章节排序号', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_report_section_order UNIQUE (report_id, order_no), 
	FOREIGN KEY(report_id) REFERENCES reports (id)
)COMMENT='报告章节表：报告正文的分章节内容' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE INDEX ix_report_sections_report_id ON report_sections (report_id);

CREATE TABLE research_events (
	id BIGINT NOT NULL COMMENT '事件ID（自增主键）' AUTO_INCREMENT, 
	run_id BIGINT NOT NULL COMMENT '所属运行批次ID', 
	sequence_no INTEGER NOT NULL COMMENT '事件序号（同一运行内严格递增）', 
	type VARCHAR(80) NOT NULL COMMENT '事件类型：node.started/search.started/evidence.created 等', 
	stage VARCHAR(80) NOT NULL COMMENT '事件所属阶段/节点名', 
	message TEXT NOT NULL COMMENT '事件可读消息', 
	payload_json MEDIUMTEXT NOT NULL COMMENT '事件负载数据 JSON', 
	severity VARCHAR(20) NOT NULL COMMENT '严重级别：info/warning/error', 
	actor VARCHAR(80) NOT NULL COMMENT '产生者：system/llm/human 等', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_run_sequence UNIQUE (run_id, sequence_no), 
	FOREIGN KEY(run_id) REFERENCES task_runs (id)
)COMMENT='研究过程事件流：节点进度与业务事件，前端时间线的数据源' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE INDEX ix_research_events_run_id ON research_events (run_id);
CREATE INDEX ix_research_events_severity ON research_events (severity);
CREATE INDEX ix_research_events_type ON research_events (type);

CREATE TABLE review_decisions (
	id BIGINT NOT NULL COMMENT '决策ID（自增主键）' AUTO_INCREMENT, 
	claim_id BIGINT NOT NULL COMMENT '被审核的结论ID', 
	decision VARCHAR(40) NOT NULL COMMENT '审核动作：accept/reject/mark_uncertain', 
	reason TEXT NOT NULL COMMENT '审核理由（必填）', 
	previous_status VARCHAR(40) COMMENT '审核前状态', 
	resulting_status VARCHAR(40) COMMENT '审核后状态', 
	reviewed_by VARCHAR(80) NOT NULL COMMENT '审核人标识', 
	created_at DATETIME NOT NULL COMMENT '审核时间', 
	PRIMARY KEY (id), 
	FOREIGN KEY(claim_id) REFERENCES claims (id)
)COMMENT='人工审核决策表：对风险 Claim 的每次审核动作留痕' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE INDEX ix_review_decisions_claim_id ON review_decisions (claim_id);

CREATE TABLE source_artifacts (
	id BIGINT NOT NULL COMMENT '工件ID（自增主键）' AUTO_INCREMENT, 
	source_id BIGINT NOT NULL COMMENT '所属来源ID', 
	artifact_type VARCHAR(40) NOT NULL COMMENT '工件类型：snapshot/original 等', 
	object_key TEXT NOT NULL COMMENT 'ArtifactStorage 对象键，如 snapshots/{task_id}/{source_id}.html', 
	sha256 VARCHAR(80) NOT NULL COMMENT '文件内容 SHA256（完整性校验/去重锚点）', 
	content_type VARCHAR(120) NOT NULL COMMENT '文件 MIME 类型', 
	size_bytes INTEGER NOT NULL COMMENT '文件大小（字节）', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_source_artifact_type UNIQUE (source_id, artifact_type), 
	FOREIGN KEY(source_id) REFERENCES sources (id)
)COMMENT='来源原始工件表：来源的 HTML 快照等原始文件在 ArtifactStorage 中的定位记录' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE INDEX ix_source_artifacts_source_id ON source_artifacts (source_id);

CREATE TABLE workflow_checkpoints (
	id BIGINT NOT NULL COMMENT '检查点ID（自增主键）' AUTO_INCREMENT, 
	run_id BIGINT NOT NULL COMMENT '所属运行批次ID', 
	sequence_no INTEGER NOT NULL COMMENT '检查点序号（同一运行内递增）', 
	node_name VARCHAR(80) NOT NULL COMMENT '节点名，如 search/fetch/extract', 
	resume_node VARCHAR(80) NOT NULL COMMENT '恢复执行时的起始节点（可与 node_name 不同）', 
	status VARCHAR(40) NOT NULL COMMENT '节点执行状态', 
	input_summary_json MEDIUMTEXT NOT NULL COMMENT '节点输入摘要 JSON', 
	output_summary_json MEDIUMTEXT NOT NULL COMMENT '节点输出摘要 JSON', 
	state_json MEDIUMTEXT NOT NULL COMMENT '恢复所需的工作流状态 JSON', 
	error_summary TEXT COMMENT '节点失败错误摘要', 
	retry_count INTEGER NOT NULL COMMENT '重试次数', 
	created_at DATETIME NOT NULL COMMENT '创建时间', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_workflow_checkpoint_sequence UNIQUE (run_id, sequence_no), 
	FOREIGN KEY(run_id) REFERENCES task_runs (id)
)COMMENT='工作流检查点：记录每个节点完成状态，用于失败后断点恢复' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE INDEX ix_workflow_checkpoints_node_name ON workflow_checkpoints (node_name);
CREATE INDEX ix_workflow_checkpoints_resume_node ON workflow_checkpoints (resume_node);
CREATE INDEX ix_workflow_checkpoints_run_id ON workflow_checkpoints (run_id);
CREATE INDEX ix_workflow_checkpoints_status ON workflow_checkpoints (status);

CREATE TABLE claim_evidence (
	id BIGINT NOT NULL COMMENT '关联ID（自增主键）' AUTO_INCREMENT, 
	claim_id BIGINT NOT NULL COMMENT '结论ID', 
	evidence_id BIGINT NOT NULL COMMENT '证据ID', 
	relation VARCHAR(40) NOT NULL COMMENT '关联关系：supports/conflicts', 
	weight FLOAT NOT NULL COMMENT '关联权重（影响覆盖度计算）', 
	PRIMARY KEY (id), 
	CONSTRAINT uq_claim_evidence_relation UNIQUE (claim_id, evidence_id, relation), 
	FOREIGN KEY(claim_id) REFERENCES claims (id), 
	FOREIGN KEY(evidence_id) REFERENCES evidence (id)
)COMMENT='结论-证据关联表：Claim 必须绑定 Evidence 的落地（证据链核心约束）' ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE INDEX ix_claim_evidence_claim_id ON claim_evidence (claim_id);
CREATE INDEX ix_claim_evidence_evidence_id ON claim_evidence (evidence_id);
