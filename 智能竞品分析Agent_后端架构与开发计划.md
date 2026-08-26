# 智能竞品分析 Agent 后端架构与 MVP 开发计划

## 1. 架构结论

MVP 采用 A 方案：

```text
FastAPI API + Celery Worker + Redis 队列 + LangGraph 工作流 + MySQL 事实库 + Elasticsearch 检索索引 + MinIO/S3 快照存储
```

首个可开发版本先跑通“证据闭环”，而不是一次性实现完整自治 Agent：

```text
创建研究任务
-> 确认研究范围
-> 后台执行研究工作流
-> 沉淀 Source / Evidence / Claim
-> 处理冲突和未披露项
-> 生成带引用报告
```

核心原则：

1. **证据优先**：报告只能基于已入库的 Claim 和 Evidence 生成。
2. **MySQL 是事实来源**：任务、证据、结论、报告和审阅决定以 MySQL 为准。
3. **ES 可重建**：Elasticsearch 只负责全文和向量召回，不保存唯一事实。
4. **对象存储保留原始材料**：HTML 快照、截图、上传文件和导出件进入 MinIO/S3。
5. **长任务进队列**：搜索、抓取、解析、抽取、验证、报告生成都不占用 API 进程。
6. **工作流可恢复**：每个节点结束后写领域对象、写检查点、写事件。
7. **人审是能力，不是异常**：冲突、低置信度、未披露项进入审阅队列。

当前仓库已新增 `backend/` MVP 骨架。为降低本地启动成本，默认使用 SQLite 和内联任务模式；生产或联调时通过环境变量切换到 MySQL、Redis 和 Celery。

---

## 2. 技术栈

| 领域 | MVP 选型 | 说明 |
|---|---|---|
| API 服务 | FastAPI + Pydantic | REST API、SSE 事件、OpenAPI 文档 |
| ORM | SQLAlchemy 2 | 同一套模型支持 SQLite 本地开发与 MySQL 部署 |
| 异步任务 | Celery + Redis | 后台执行长任务、重试、并发 |
| 工作流编排 | LangGraph | 后续承载可恢复研究状态机；当前 MVP 先保留服务边界 |
| 主数据库 | MySQL 8.0 | 生产事实库；本地默认 SQLite |
| 检索索引 | Elasticsearch | Evidence 全文检索、向量召回、相似去重 |
| 对象存储 | MinIO / S3 | HTML 快照、截图、上传材料、导出文件 |
| 网页抓取 | httpx + Playwright | 静态网页优先，必要时动态渲染 |
| 正文解析 | Trafilatura / Readability | 网页正文、标题、时间、段落定位 |
| 文档解析 | PyMuPDF、python-docx、python-pptx、openpyxl | PDF、Word、PPT、Excel |
| LLM 网关 | Provider Adapter + Pydantic Schema | 统一模型调用、结构化输出、校验和审计 |

MVP 不引入 Kubernetes、Temporal、复杂 RBAC、付费数据源和社媒深度采集。

---

## 3. 总体架构

```mermaid
flowchart LR
    UI["Vue 前端工作台"] --> API["FastAPI API / SSE"]
    API --> DB[("MySQL / SQLite<br/>事实库")]
    API --> REDIS[("Redis")]
    API --> QUEUE["Celery Queue"]
    API --> OBJ["MinIO / S3"]
    API --> ES[("Elasticsearch")]

    QUEUE --> WF["Research Workflow<br/>LangGraph"]
    WF --> SEARCH["Search Connector"]
    WF --> FETCH["Fetch & Snapshot"]
    WF --> PARSE["Parse Service"]
    WF --> EXTRACT["LLM Extraction"]
    WF --> VERIFY["Claim Verification"]
    WF --> REPORT["Report Generator"]

    SEARCH --> WEB["公开网页 / 数据源"]
    FETCH --> WEB
    FETCH --> OBJ
    PARSE --> DB
    EXTRACT --> DB
    VERIFY --> DB
    REPORT --> DB
    PARSE --> ES
    WF --> API
```

### 3.1 服务边界

首版采用“模块化单体 + Worker”，不拆微服务：

```text
backend/
  app/
    api/            # REST、SSE、接口路由
    models.py       # SQLAlchemy 领域模型
    schemas.py      # Pydantic API 契约
    services/       # 任务、事件、证据、报告服务
    workers/        # Celery app 与任务入口
    config.py       # 环境变量配置
    db.py           # 数据库连接与 Session
  tests/
```

API 层只做用户请求、查询和事件流；Worker 层执行所有超过 1 秒的研究动作；服务层负责领域规则和幂等写入。

---

## 4. MVP 工作流

### 4.1 第一阶段：可跑通闭环

当前后端先实现确定性 demo workflow，用来验证前后端契约：

```text
POST /v1/research-tasks
-> POST /v1/research-tasks/{id}/confirm
-> 创建 TaskRun
-> 产生 research_events
-> 写入 Source / Evidence / Claim
-> 生成 Report 草稿
-> 任务进入 waiting_review
```

这一步的价值是先让前端从静态 mock 数据切换到真实 API 数据，同时验证核心表关系、事件流和引用详情。

### 4.2 第二阶段：替换真实节点

demo workflow 之后逐步替换为真实节点：

| 节点 | 职责 | 实现方式 |
|---|---|---|
| `plan_research` | 解析 Prompt、竞品、维度、预算 | LLM 结构化输出 + 规则校验 |
| `build_search_plan` | 生成搜索关键词、站点优先级 | LLM + 模板策略 |
| `discover_sources` | 发现候选 URL | 搜索 API 适配器 |
| `fetch_source` | 抓取网页、保存 HTML/截图 | httpx + Playwright + MinIO |
| `parse_source` | 提取正文和定位信息 | Trafilatura / Readability |
| `extract_evidence` | 抽取 Evidence 和候选 Claim | LLM Schema 输出 |
| `verify_claims` | 去重、冲突检测、置信度评分 | 规则优先，LLM 解释 |
| `review_gate` | 暂停等待用户审阅 | 数据库状态 + API 操作 |
| `generate_report` | 生成 Markdown 报告 | 只输入已验证 Claim/Evidence |
| `validate_report` | 引用覆盖和错配检查 | 确定性规则 |

### 4.3 事件类型

| 类型 | 用途 |
|---|---|
| `planning.started` | 需求解析开始 |
| `search.started` | 检索计划开始 |
| `source.found` | 新来源发现 |
| `source.fetched` | 来源抓取完成 |
| `evidence.created` | 新证据入库 |
| `claim.created` | 新 Claim 入库 |
| `claim.conflict_detected` | 发现冲突 |
| `review.required` | 需要人工审阅 |
| `report.created` | 报告草稿生成 |
| `report.published` | 报告签发 |
| `task.failed` | 任务失败 |

---

## 5. 数据模型

### 5.1 核心关系

```mermaid
erDiagram
    RESEARCH_TASK ||--o{ TASK_RUN : has
    TASK_RUN ||--o{ RESEARCH_EVENT : emits
    RESEARCH_TASK ||--o{ SOURCE : collects
    SOURCE ||--o{ SOURCE_ARTIFACT : stores
    SOURCE ||--o{ EVIDENCE : contains
    RESEARCH_TASK ||--o{ CLAIM : produces
    CLAIM }o--o{ EVIDENCE : supported_by
    CLAIM ||--o{ REVIEW_DECISION : reviewed_by
    RESEARCH_TASK ||--o{ REPORT : generates
    REPORT ||--o{ REPORT_SECTION : contains
```

### 5.2 MVP 表

| 表 | 说明 |
|---|---|
| `research_tasks` | 用户创建的一次研究任务 |
| `task_runs` | 每次执行记录，支持重跑 |
| `research_events` | 前端可审计事件流 |
| `sources` | 来源 URL、类型、发布方、抓取时间、索引状态 |
| `source_artifacts` | HTML 快照、截图、上传原文件、导出件 |
| `evidence` | 可引用原文片段和定位器 |
| `claims` | 结构化结论，包含状态和置信度 |
| `claim_evidence` | Claim 与 Evidence 的支持、反驳、补充关系 |
| `review_decisions` | 用户审阅决定 |
| `reports` | 报告版本和引用覆盖率 |
| `report_sections` | 报告章节 Markdown |
| `uploads` | 用户上传材料记录 |

### 5.3 Claim 结构

Claim 不能只存自然语言，需要结构化字段：

```json
{
  "subject": "Cursor",
  "predicate": "supports_feature",
  "value": {
    "feature": "privacy_mode",
    "plan": "business"
  },
  "claim_type": "feature_support",
  "status": "verified",
  "confidence": "high",
  "confidence_score": 0.87
}
```

自然语言只用于展示，结构字段用于去重、对比、矩阵和报告引用。

---

## 6. API 契约

当前 MVP 已实现：

| API | 方法 | 说明 |
|---|---|---|
| `/v1/health` | GET | 健康检查 |
| `/v1/research-tasks` | POST | 创建研究任务 |
| `/v1/research-tasks` | GET | 任务列表 |
| `/v1/research-tasks/{id}` | GET | 任务详情，含 Source/Evidence/Claim/Report |
| `/v1/research-tasks/{id}/confirm` | POST | 确认范围并启动 run |
| `/v1/research-tasks/{id}/runs` | POST | 重跑任务 |
| `/v1/research-tasks/{id}/events` | GET | 拉取事件列表 |
| `/v1/research-tasks/{id}/events/stream` | GET | SSE 事件流 |
| `/v1/sources/{id}` | GET | 来源详情 |
| `/v1/evidence/{id}` | GET | 证据详情 |
| `/v1/claims/{id}` | GET | Claim 详情 |
| `/v1/claims/{id}/review` | POST | 提交审阅决定 |
| `/v1/reports/{id}` | GET | 报告详情 |
| `/v1/reports/{id}/export` | POST | 导出 Markdown 内容 |

---

## 7. 可靠性设计

### 7.1 幂等键

| 操作 | 幂等键 |
|---|---|
| 创建 Source | `organization_id + canonical_url + retrieved_at_bucket` |
| 保存快照 | `source_id + sha256` |
| 创建 Evidence | `source_id + locator + quote_hash` |
| 创建 Claim | `task_id + subject + predicate + normalized_value` |
| 发送事件 | `run_id + sequence_no` |
| 生成报告版本 | `task_id + run_id + version` |

### 7.2 失败处理

| 失败 | 策略 |
|---|---|
| 搜索超时 | 指数退避重试，失败后换关键词 |
| 单 URL 抓取失败 | 记录失败事件，继续其他来源 |
| 动态页面失败 | 回退静态抓取或搜索摘要 |
| 文档解析失败 | 保留原文件，标记解析失败 |
| LLM 输出不合法 | Schema 校验失败后重试一次 |
| 引用覆盖不足 | 阻止签发，进入审阅 |
| Worker 重启 | 从最近检查点恢复 |

### 7.3 报告质量门槛

- 事实性陈述引用覆盖率 >= 90%。
- 每个引用能回到 Evidence。
- Evidence 能回到 Source 和快照。
- 冲突、低置信度、未披露项不能写成确定事实。
- 高风险字段需要官方来源或两个独立高质量来源。

---

## 8. 开发阶段

### 阶段 0：API 外壳与 demo workflow

已开始实现。

交付：

- FastAPI 项目骨架。
- SQLAlchemy 领域模型。
- 创建任务、确认任务、任务详情、事件、证据、Claim、报告 API。
- Celery worker 入口。
- SQLite 默认本地运行。
- Docker Compose 提供 MySQL、Redis、Elasticsearch、MinIO。

验收：

- 可以创建研究任务。
- 可以确认任务并生成 demo Evidence、Claim、Report。
- 可以查看事件流和引用详情。

### 阶段 1：真实公开网页研究

交付：

- 搜索适配器。
- httpx 抓取。
- HTML 快照保存。
- Trafilatura 正文解析。
- LLM Schema 抽取 Evidence/Claim。
- ES Evidence 索引。

### 阶段 2：验证与审阅

交付：

- Source 去重。
- Claim 合并。
- 置信度评分。
- 冲突检测。
- 审阅 API 完整化。
- 报告签发质量门槛。

### 阶段 3：产品化

交付：

- 文件上传和文档解析。
- 任务暂停、恢复、取消。
- 报告版本管理。
- PDF/Markdown 导出。
- OpenTelemetry 和 Langfuse。
- 回归测试集。

---

## 9. 当前不做

- 不做无限自主多 Agent。
- 不做十几个微服务。
- 不让 LLM 直接根据网页全文生成最终报告。
- 不把向量库当事实库。
- 不接付费数据库。
- 不做大规模社媒抓取。
- 不做复杂企业权限。

---

## 10. 本地运行方式

后端目录：

```text
backend/
```

启动 API：

```powershell
cd backend
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

默认 `.env`：

```text
DATABASE_URL=sqlite:///./verda_dev.db
TASK_MODE=inline
```

切到 Celery：

```text
TASK_MODE=celery
```

启动 Worker：

```powershell
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```

启动基础设施：

```powershell
cd backend
docker compose up -d
```

MySQL 连接示例：

```text
DATABASE_URL=mysql+pymysql://verda:verda@localhost:3306/verda
```

