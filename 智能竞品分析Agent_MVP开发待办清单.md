# 智能竞品分析 Agent MVP 开发待办清单

## 一、项目目标

完成一个可运行、可演示、可扩展的智能竞品分析 Agent MVP。

目标演示链路：

> 创建研究任务 → 确认任务 → 执行研究流程 → 查看执行进度 → 查看证据 → 审核结论 → 查看并导出分析报告

当前项目已经完成前后端 MVP 闭环，并推进到真实信息采集、结构化 Claim 分析、结构化报告生成和人工审核闭环。下一阶段不再以继续堆叠零散功能为主，而是进入 Agent 工作流升级：参考 DeerFlow 的长任务设计，把当前线性研究流程改造成可观察、可恢复、可扩展的竞品研究 Agent 流水线。

后续开发主线：

> 先稳住现有闭环 → 引入 LangGraph 最小工作流 → 拆节点和事件 → 增加 checkpoint / 恢复 → 再做真实异步和基础设施升级

目标产品形态补充：

> 对话输入调研需求 → Agent 追问研究范围和权重 → 用户确认后启动真实研究 → 实时展示研究过程 → 聚合网页、新闻和舆情证据 → 点击证据可溯源 → 用户审核结论质量 → 基于审核结果生成可导出的报告

因此后续开发不再只按纯技术阶段推进，而是优先把“研究工作台”体验补齐：先让每条结论更可信、每条证据更可追溯、每一步研究过程更可观察，再扩展社交舆情和生产级基础设施。

---

## 二、总体技术路线

- [x] FastAPI 作为后端 API 框架
- [x] Celery 作为异步任务执行方案
- [x] Redis 作为消息队列和任务结果存储
- [x] LangGraph 作为后续 Agent 工作流编排方案
- [x] SQLite 作为 MVP 默认数据库
- [ ] MySQL 作为正式数据库
- [ ] Elasticsearch 作为资料检索和全文搜索引擎
- [ ] MinIO / S3 作为网页快照和报告文件存储
- [x] Vue 作为前端技术栈

当前技术判断：

- LangGraph 是下一阶段最高优先级，用于替换 `simulate_research_run` 中不断变长的线性流程。
- MySQL、Elasticsearch、MinIO / S3 暂时后置，等工作流节点边界稳定后再接入。
- Celery 已有入口，但应在 LangGraph 接入后再升级为真正可控的异步执行层。
- 前端短期保持现有 API 合约不变，避免工作流升级和界面改造同时放大风险。

---

## 三、阶段 0：项目基线确认

### 目标

确定项目结构、技术路线、数据模型和最小可运行环境。

### 任务

- [x] 完成产品需求和原型文档
- [x] 完成 A 方案后端架构设计
- [x] 创建后端基础目录结构
- [x] 创建 FastAPI 应用入口
- [x] 创建数据库连接和基础模型
- [x] 创建 API Schema
- [x] 创建研究任务服务层
- [x] 创建 Celery 任务入口
- [x] 创建 Docker Compose 基础设施配置
- [x] 创建后端 API 合约测试
- [x] 验证本地开发环境可启动
- [x] 统一项目启动说明
- [x] 补充项目根目录 README

---

## 四、阶段 1：MVP 前后端闭环

### 目标

让用户可以通过前端完成一次完整的竞品分析任务。

### 后端任务

- [x] 增加 CORS 配置，支持前端本地开发访问
- [x] 统一 API 错误响应格式
- [x] 完善任务状态转换规则
- [x] 增加任务执行失败状态和错误信息
- [x] 增加开发环境 Demo 数据重置能力
- [x] 增加前端所需的分页和筛选参数

### 前端任务

- [x] 创建前端 API 请求封装
- [x] 将静态任务数据替换为后端接口数据
- [x] 接入创建研究任务接口
- [x] 接入确认研究任务接口
- [x] 接入任务详情接口
- [x] 接入任务事件列表接口
- [x] 接入 SSE 事件流接口或轮询机制
- [x] 展示任务执行状态
- [x] 展示研究来源
- [x] 展示证据内容
- [x] 展示分析结论
- [x] 展示结论审核状态
- [x] 展示分析报告
- [x] 接入报告导出接口
- [x] 增加加载状态
- [x] 增加错误状态
- [x] 增加空数据状态

### 验收标准

- [x] 用户可以在前端创建一个竞品分析任务
- [x] 用户可以确认任务并启动研究
- [x] 用户可以看到任务执行过程
- [x] 用户可以看到来源、证据和结论
- [x] 用户可以审核结论
- [x] 用户可以查看并导出报告
- [x] 前后端联调流程可以重复执行

---

## 五、阶段 2：任务和数据模型完善

### 目标

建立稳定的数据结构和业务状态流转，为真实研究能力做准备。

### 任务

- [x] 固化研究任务状态：
  - [x] `draft`
  - [x] `confirmed`
  - [x] `queued`
  - [x] `running`
  - [x] `waiting_review`
  - [x] `completed`
  - [x] `failed`
- [x] 完善 ResearchTask 字段
- [x] 完善 Source 字段
- [x] 完善 Evidence 字段
- [x] 完善 Claim 字段
- [x] 完善 Report 字段
- [x] 增加 Claim 与 Evidence 的关联关系
- [x] 增加人工审核字段
- [x] 增加报告版本字段
- [x] 增加研究事件日志字段
- [x] 增加数据库唯一约束和索引
- [x] 增加 Alembic 数据库迁移
- [x] 补充模型层测试
- [x] 补充核心服务层测试

---

## 六、阶段 3：真实信息采集能力

### 目标

将当前 Demo 数据替换为真实的搜索、网页抓取和内容解析流程。

### 任务

- [x] 定义 Search Adapter 接口
- [x] 接入第一个搜索服务
- [x] 实现搜索结果标准化
- [x] 实现网页抓取模块
- [x] 增加请求超时控制
- [x] 增加失败重试机制
- [x] 增加访问频率限制
- [x] 增加 robots 和合规策略
- [x] 实现 HTML 快照保存
- [ ] 接入 MinIO / S3 存储
- [x] 实现网页正文抽取
- [x] 接入 Trafilatura 或同类正文解析工具
- [x] 清洗正文内容
- [x] 保存网页元数据
- [x] 生成标准化 Source 和 Evidence
- [x] 增加采集质量检查

阶段 3A MVP 说明：

- 已接入 Tavily Search Adapter，并支持没有 API Key 时从任务文本或 source_preferences 中提取手动 URL。
- 已实现真实网页抓取、HTML 本地快照、基础正文解析、Evidence 片段抽取和 Source / Evidence 入库。
- 已补充失败重试、域名级基础频率限制、robots.txt 检查、页面大小限制和低质量正文过滤。
- 已接入 Trafilatura 作为优先正文抽取器，并保留标准库解析器作为 fallback。
- 暂未实现 MinIO / S3，本阶段个人项目先继续使用本地快照存储。

---

## 七、阶段 4：LLM 结构化分析能力

### 目标

从真实网页和证据中提取可验证的竞品事实，并生成分析结论。

### 任务

- [x] 定义竞品信息抽取 Schema
- [x] 定义价格信息 Schema
- [x] 定义功能信息 Schema
- [x] 定义市场定位 Schema
- [x] 定义优劣势分析 Schema
- [x] 实现结构化 LLM 抽取
- [x] 增加 JSON Schema 校验
- [x] 增加异常输出修复
- [x] 为每条 Claim 绑定 Evidence
- [x] 增加引用完整性检查
- [x] 增加结论置信度字段
- [x] 增加无证据结论拦截
- [x] 设计人工审核流程
- [x] 生成结构化分析报告
- [x] 增加报告模板
- [x] 增加报告生成失败重试

阶段 4A MVP 说明：

- 已新增 OpenAI-compatible LLM Provider 抽象，配置 API Key 后可切到真实结构化抽取。
- 无 LLM API Key 时使用规则抽取 fallback，保证本地开发和离线测试可运行。
- Claim 输出通过 Pydantic / JSON Schema 校验后入库，并强制绑定已存在 Evidence。

阶段 4B MVP 说明：

- 已增加 LLM 异常输出修复，支持 fenced JSON、说明文字包裹、顶层数组、常见枚举别名和字符串置信度分数修复。
- 已增加结构化报告模板，固定输出执行摘要、采集摘要、关键结论、风险与待审阅项、引用覆盖等章节。
- 已增加报告生成失败重试，失败会写入 `report.generate_failed` 事件，成功后继续进入审阅流程。

---

## 八、阶段 5：Agent 工作流升级（下一阶段主线）

### 目标

将当前集中在 `research_service.simulate_research_run` 的线性研究流程，升级为可观察、可恢复、可扩展的 LangGraph 工作流。

本阶段的关键原则：

1. **保持产品闭环不变**：前端创建任务、确认任务、查看事件、查看证据、审核 Claim、导出报告的 API 合约先不变。
2. **先包装，后重构**：第一版 LangGraph 节点可以复用现有 `collection.py`、`claim_extractor.py`、`reporting.py` 能力，不急着拆到最细。
3. **节点可观测优先**：每个节点必须写入开始、成功、失败事件，方便前端时间线和后续排障。
4. **证据链不能退化**：任何 Claim 仍必须绑定 Evidence；报告仍只能基于已入库 Claim / Evidence 生成。
5. **DeerFlow 思路垂直化**：借鉴长任务、节点、checkpoint、恢复、skills 思路，但不照搬通用 Super Agent 的全部复杂度。

### 当前问题

- 当前主流程由 `simulate_research_run` 串联，功能可用但职责过重。
- Celery 入口只是异步调用同一条线性流程，缺少节点级重试、恢复和取消。
- `ResearchEvent` 已经存在，但还没有形成统一的节点生命周期事件规范。
- 缺少 checkpoint，长任务中途失败后只能重跑。
- 现有测试主要覆盖 API 合约，工作流级回归保护还不够。

### 任务

### 5.0 基线保护

- [x] 确认项目版本管理方式，建议初始化 git 或建立明确备份策略
  - 当前项目根目录未发现 `.git`，本轮未自动初始化版本库；进入 LangGraph 改造前建议初始化 git 或建立明确备份策略。
- [x] 跑通现有后端测试：`.\backend\.venv\Scripts\python.exe -m pytest`
- [x] 跑通前端构建：`npm run build`
- [x] 补充一条完整研究流程回归测试：创建任务 → 确认 → 生成 Source / Evidence / Claim / Report → 进入 `waiting_review`
- [x] 固化当前 API 合约，避免 LangGraph 升级时破坏前端
- [x] 清理或归档临时数据库、日志、缓存文件，保证开发环境可复现
  - 已新增 `backend/scripts/cleanup_dev_artifacts.py`，默认 dry-run 列出本地数据库、日志、pytest 缓存和前端构建产物，只有显式 `--apply` 才会删除。
  - 已新增根目录 `.gitignore`，统一忽略本地数据库、日志、缓存、虚拟环境、依赖目录和前端构建产物。

### 5.1 LangGraph 最小接入

- [x] 新增工作流目录：`backend/app/workflows/`
- [x] 新增 `ResearchWorkflowState`，承载 `task_id`、`run_id`、`scope`、`summary`、`errors`、`current_node`
- [x] 新增 `research_graph.py`，构建最小 LangGraph
- [x] 新增工作流入口函数：`run_research_workflow(db, run_id)`
- [x] 保留 `simulate_research_run` 作为兼容入口，内部逐步切到 workflow
- [x] 更新 Celery task，调用新的 workflow 入口
- [x] 保持 `TASK_MODE=inline` 和 `TASK_MODE=celery` 两种模式可用
- [x] 增加缺少 LangGraph 依赖时的清晰启动错误

第一版节点建议：

```text
initialize_run
-> plan_research
-> collect_sources_and_evidence
-> extract_claims
-> generate_report
-> review_gate
```

说明：第一版先把搜索、抓取、解析、Evidence 抽取合并在 `collect_sources_and_evidence`，复用现有 `collect_research_evidence`，避免一次拆得过碎。

### 5.2 节点拆分和事件规范

- [x] 定义统一节点生命周期事件：
  - [x] `node.started`
  - [x] `node.succeeded`
  - [x] `node.failed`
  - [x] `node.skipped`
  - [x] `node.retrying`
- [x] 每个节点写入 `stage`、`node_name`、`duration_ms`、`input_summary`、`output_summary`
- [x] 将 `plan_research` 独立为任务理解节点
- [x] 将 `collect_sources_and_evidence` 独立为采集与 Evidence 生成聚合节点
- [x] 将 `discover_sources` 独立为搜索节点
- [x] 将 `fetch_sources` 独立为网页抓取节点
- [x] 将 `parse_sources` 独立为正文解析节点
- [x] 将 `extract_evidence` 独立为 Evidence 抽取节点
- [x] 将 `extract_claims` 独立为 Claim 抽取节点
- [x] 将 `verify_claims` 独立为引用完整性、置信度和冲突检查节点
- [x] 将 `generate_report` 独立为报告生成节点
- [x] 将 `review_gate` 独立为人工审核等待节点
- [x] 前端时间线继续消费 `ResearchEvent`，不新增前端专用接口

5.2A MVP 说明：
- 已在 LangGraph 工作流层新增节点生命周期事件规范，并为当前 `run_legacy_research_flow` 节点写入 `node.started`、`node.succeeded` 和 `node.failed`。
- 节点事件 payload 已包含 `stage`、`node_name`、`duration_ms`、`input_summary`、`output_summary`，失败事件额外包含 `error`。
- 现有业务事件仍写入 `ResearchEvent`，前端可继续通过同一事件接口消费；后续再把线性流程拆成更多独立节点。

5.2B MVP 说明：
- 已将 LangGraph 工作流从单个 `run_legacy_research_flow` 节点拆成 `initialize_run`、`plan_research`、`collect_sources_and_evidence`、`extract_claims`、`generate_report`、`review_gate` 六个节点。
- `collect_sources_and_evidence` 仍复用现有采集服务，暂时聚合搜索、抓取、解析和 Evidence 抽取；后续再继续拆细 `discover_sources`、`fetch_sources`、`parse_sources` 和 `extract_evidence`。
- 现有业务事件顺序和 API 闭环保持兼容，节点生命周期事件作为追加观测信息写入同一个 `ResearchEvent`。

5.2C MVP 说明：
- 已将 `collect_sources_and_evidence` 聚合节点拆成 `discover_sources`、`fetch_sources`、`parse_sources`、`extract_evidence` 四个 LangGraph 节点。
- 采集服务已拆出 `discover_research_sources`、`fetch_research_sources`、`parse_research_sources`、`extract_research_evidence` helper；旧的 `collect_research_evidence` 继续作为兼容入口串联这些 helper。
- 前端仍通过统一 `ResearchEvent` 消费业务事件和节点生命周期事件，未新增前端专用接口。

5.2D MVP 说明：
- 已将 `verify_claims` 独立为 LangGraph 节点，位于 `extract_claims` 和 `generate_report` 之间。
- `extract_claims` 只负责生成 Claim；`verify_claims` 负责引用完整性、低置信度和冲突风险的基础检查，并统一写入 `claim.created` 业务事件。
- 节点失败会写入 `node.failed`，前端后续可在研究时间线中定位 Claim 校验失败原因。

5.2E MVP 说明：
- 前端运行页左侧“研究时间线”已改为消费同一个 `ResearchEvent` 列表中的 `node.started`、`node.succeeded`、`node.failed`、`node.skipped` 和 `node.retrying` 事件。
- 新增 `researchTimeline` 事件聚合模块，将后端节点生命周期事件合并为节点状态卡片，展示节点名称、状态、耗时、输出摘要和失败原因。
- 暂未新增前端专用接口；没有真实任务事件时仍保留演示态，方便前端离线预览。

目标节点形态：

```text
initialize_run
-> plan_research
-> build_search_plan
-> discover_sources
-> fetch_sources
-> parse_sources
-> extract_evidence
-> extract_claims
-> verify_claims
-> generate_report
-> review_gate
```

### 5.3 checkpoint 和恢复

- [x] 设计最小 checkpoint 结构，可以先存入 `TaskRun.input_snapshot_json` 或新增 `workflow_checkpoints`
- [x] 每个节点成功后保存 checkpoint
- [x] 记录节点输入摘要、输出摘要、错误摘要和重试次数
- [x] 支持失败任务从最近成功节点继续
- [x] 支持 `waiting_review` 后继续执行报告重生成或签发
- [x] 支持幂等写入 Source / Evidence / Claim / Report，避免恢复后重复数据
- [x] 增加 checkpoint 清理策略，避免数据库无限增长

5.3A MVP 说明：
- 已新增 `WorkflowCheckpoint` / `workflow_checkpoints`，保存 `run_id`、`node_name`、`resume_node`、节点输入摘要、输出摘要、可序列化状态和重试次数字段。
- LangGraph 节点成功后会写入 checkpoint；节点失败时会保留失败节点名为 `TaskRun.current_stage`，并将 run / task 标记为 `failed`，方便后续定位恢复点。
- `run_research_workflow(..., resume=True)` 会从最近成功 checkpoint 的 `resume_node` 继续执行，并从数据库重建 Source / Evidence / Claim 计数，避免依赖不可持久化的内存对象。
- 已补充恢复回归测试，覆盖 `verify_claims` 首次失败后从 `extract_claims` checkpoint 继续执行，且不会重复生成 Report。
- checkpoint 内的失败摘要、真实 retry 次数统计、`waiting_review` 后报告重生成、checkpoint 清理和更完整的节点级 retry 仍留到后续 5.4 / 5.5 继续开放。
- 前端任务详情轮询在任务从 `waiting_review` 走到 `completed` 且存在报告时，会自动回到报告页，方便直接查看审核后新版本。

### 5.4 失败处理、重试和取消

- [x] 定义节点级可重试异常和不可重试异常
- [x] 搜索、抓取、正文解析、LLM 抽取、报告生成分别设置重试策略
- [x] 抓取失败只影响当前 URL，不阻断整个任务
- [x] LLM Schema 修复失败后记录 `node.failed` 并进入可恢复状态
- [x] 报告生成失败继续沿用 `report.generate_failed`，并补齐节点事件
- [x] 增加任务取消 API 和状态流转
- [x] 取消任务后 Worker / workflow 能停止后续节点

5.4A MVP 说明：
- 已在 LangGraph 节点包装层新增最小 retry 策略：`discover_sources`、`fetch_sources`、`parse_sources`、`extract_evidence`、`extract_claims` 和 `generate_report` 首次失败后会写入 `node.retrying`，并再尝试一次。
- 已新增 `POST /v1/research-tasks/{task_id}/cancel`，支持将可取消任务和最新 run 流转为 `canceled`，记录 `run.canceled` 事件和取消原因。
- workflow 在每个节点开始前检查取消状态；如果任务已取消，会写入 `node.skipped` 并停止后续节点。当前是节点边界的合作式取消，不抢占正在执行的同步网络请求或 Worker 进程。
- 异常类型细分、真实 retry 次数落 checkpoint、LLM Schema 失败恢复和 Worker 级中断留到 5.4B / 5.6 继续开放。

5.4B MVP 说明：
- 已新增 `is_retryable_workflow_error`，将临时网络/限流/超时类错误视为可重试，将工作流状态缺失、任务不存在、Schema 类错误和 `report_generation_failed` 视为不可重试。
- 节点重试成功后，`WorkflowCheckpoint.retry_count` 会记录该节点真实重试次数，checkpoint 状态摘要中也会写入 `node_retry_counts`。
- 报告生成继续沿用 `generate_report_with_retry` 的 `report.generate_failed` 事件；当内部重试全部失败时，workflow 不再外层重跑报告节点，而是补齐 `generate_report` 的 `node.failed` 事件。
- LLM Schema 失败目前已纳入不可重试分类标记，但还缺少专门的端到端恢复测试，后续 5.4C 可继续补齐。

5.4C MVP 说明：
- 已新增失败 checkpoint：节点最终失败时会保存 `status=failed` 的 `WorkflowCheckpoint`，包含节点输入摘要、`retryable` 输出摘要、`error_summary`、`retry_count` 和可恢复状态快照。
- LLM schema / JSON 修复失败不再被 `extract_and_store_claims` 静默 fallback，会以 `schema_validation_failed:*` 抛给 workflow，并按不可重试失败处理。
- 已补充端到端恢复测试：`extract_claims` 首次 schema 失败后写入 `node.failed` 和失败 checkpoint，修复后可通过 `run_research_workflow(..., resume=True)` 从最近成功 checkpoint 继续完成。
5.4D MVP 说明：
- 已补充 checkpoint 恢复幂等回归测试：当 `generate_report` 已经写入 Report / `report.created`，但节点成功 checkpoint 尚未保存就失败时，恢复会从最近成功 checkpoint 继续到 `generate_report`，且不会重复生成 Report、Source、Evidence、Claim 或重复写入 `report.created` 业务事件。

### 5.5 人工审核后继续执行

- [x] 明确 Claim 审核决策对报告的影响：
  - [x] `accept`：纳入报告
  - [x] `exclude`：从报告中排除
  - [x] `mark_uncertain`：保留但降级为风险项
- [x] 增加“审核后重新生成报告”服务入口
- [x] 支持报告版本递增，而不是覆盖旧报告
- [x] 前端报告页展示当前版本和历史版本入口
- [x] 人工审核完成后可从 `review_gate` 继续到 `generate_report`

5.5 MVP 说明：
- 审核动作已明确影响报告输入：`accept` 会将 Claim 标为 verified 并纳入报告，`exclude` 会设置 `include_in_report=false`，`mark_uncertain` 会保留 Claim 入报但降级为 low_confidence 风险项。
- 新增审核完成后的报告再生成链路：当所有风险 Claim 都有终态审核决策后，服务会从 `review_gate` 推进到 `generate_report`，创建递增版本报告，并记录包含 `version` 的 `report.created` 事件。
- 报告生成保持首轮幂等，审核后显式创建新版本，不覆盖旧报告；详情接口按版本排序返回报告历史。
- 前端报告页已支持默认查看最新版本，并可在版本历史中切换旧版本；导出 Markdown 跟随当前选中版本。
- Stage 7.6A 已补充手动“重新生成”按钮，审核完成后可基于当前 Claim 状态显式生成下一版报告；版本差异对比仍后置。

### 5.6 Celery 真实异步化

- [x] Celery task 改为 workflow 执行入口
- [x] 配置 Redis broker / result backend 的开发环境默认值
- [x] 增加任务优先级字段
- [x] 增加并发控制，限制同一任务或同一用户的并发 run
- [x] 增加 worker 健康检查
- [x] 增加 worker 启动文档

5.6 MVP 说明：
- `research.run` Celery task 已直接调用 LangGraph `run_research_workflow`，API 在 `TASK_MODE=celery` 下不再同步执行研究流程，而是通过 `apply_async` 入队并立即返回 queued run。
- 已明确 Redis 默认配置：`CELERY_BROKER_URL=redis://localhost:6379/0`，`CELERY_RESULT_BACKEND=redis://localhost:6379/1`，并将默认队列设为 `research`。
- `TaskRun.priority` 已入库并通过 API 返回；confirm / rerun 支持 `?priority=0..9`，并传递给 Celery Redis priority queue。
- 同一任务的 queued / running run 会在创建 run 前被拦截，避免重复入队；当前是应用层并发保护，跨多 API 实例的数据库锁/唯一约束可留到部署强化阶段。
- 新增 `GET /v1/worker/health` 返回 API 当前 Celery 配置和注册任务名；当前健康检查验证配置可见性，不主动 ping 远端 worker。
- 后端 README 已补充 Celery 模式启动命令、队列名、优先级参数和 health check。

### 阶段 5 验收标准

- [x] 不改变前端主要交互的情况下，完整研究流程由 LangGraph workflow 执行
- [x] 每个工作流节点都有开始、成功、失败事件
- [x] 任一非致命 URL 抓取失败不会导致整条任务失败
- [x] 报告生成失败能记录节点失败和报告失败事件
- [x] 失败任务可以从最近成功节点恢复或明确重跑
- [x] 人工审核后可以继续生成新版本报告
- [x] inline 和 Celery 两种模式都能跑通核心流程

阶段 5 验收说明（基于 96 条后端测试逐项验证）：工作流节点事件（含 node.started/succeeded/failed/skipped/retrying）有专门断言；单源抓取失败跳过不中断任务、报告生成重试耗尽语义、checkpoint 恢复、审核后报告重生成均有离线 E2E 覆盖；Celery 模式经 eager 单测与 compose 编排验证，真实 Redis 联调随中间件就绪后补做（同阶段 6 策略）。

---

## 九、阶段 6：基础设施和部署（Stage 5 稳定后启动）

当前策略：中间件接入先完成配置骨架，真实 MySQL / Redis / MinIO / Elasticsearch 可访问 IP 和联调暂时搁置，待外部服务地址确认后再继续 6.2-6.6。

### 目标

从本地 Demo 环境升级到可部署、可维护的开发和测试环境。

本阶段不要早于 LangGraph 最小闭环启动。原因是数据库、队列、对象存储和检索系统都会放大工作流状态一致性问题，最好等节点边界和事件规范稳定后再接。

### 任务

### 6.1 配置和运行环境

- [x] 配置文件和环境变量分离
- [x] 区分 `dev`、`test`、`prod` 配置
- [x] 明确本地默认模式：SQLite + inline workflow
- [x] 明确联调模式：MySQL + Redis + Celery
- [x] 明确演示模式：Docker Compose 一键启动
- [x] 更新 `.env.example`
- [x] 更新后端启动文档

6.1 MVP 说明：
- 新增 `APP_ENV=dev|test|prod` profile 归一逻辑，保留显式环境变量优先级；`ENVIRONMENT=development/local/testing/production` 会归一到对应 profile。
- `dev` 默认使用 SQLite + inline workflow，维持本地开发和离线 Demo 体验。
- `test` 默认使用独立 SQLite 文件和 Redis DB 编号，避免自动化测试与开发数据互相污染。
- `prod` 默认指向 MySQL + Redis + Celery，作为 Docker / 部署式联调的基础配置。
- 已补齐 MySQL、Redis、Elasticsearch、MinIO 的环境变量入口；MySQL / Redis 支持通过 host、port、DB 编号和凭证自动组合连接 URL，方便后续直接替换为真实可访问 IP。
- 当前 `docker-compose.yml` 仍以 MySQL、Redis、Elasticsearch、MinIO 等基础设施服务为主；完整前后端容器一键启动留到 6.6 继续开放。
- `.env.example` 和后端 README 已补充 profile、覆盖规则、Celery worker 启动和 Docker Compose 边界说明。

### 6.2 MySQL 和迁移

- [ ] 从 SQLite 切换到 MySQL 的配置验证
- [ ] 检查 SQLAlchemy 字段类型在 MySQL 下的兼容性
- [ ] 完成数据库迁移脚本
- [ ] 增加 MySQL 下的模型层测试
- [ ] 增加迁移回归测试
- [ ] 明确本地 SQLite 数据不作为生产事实库

### 6.3 Redis / Celery

- [x] 配置 Redis Broker
- [x] 配置 Celery result backend
- [x] 配置 Celery Worker
- [ ] 配置 Celery Beat，按需执行定时任务（当前产品无定时任务需求，暂缓）
- [x] 增加 worker 健康检查
- [x] 增加 Celery 任务测试
- [x] 文档化 worker 启动、重启和失败排查流程

6.3 MVP 说明：Broker / result backend / worker 配置与任务入队链路已在 5.6 完成并有 eager 模式单测覆盖；worker 健康检查 `GET /v1/worker/health`；启动命令在后端 README，失败排查见 docs/排障手册。真实 Redis 联调随中间件就绪后验证（当前策略）。

### 6.4 MinIO / S3

- [x] 抽象 ArtifactStorage 接口，保留 Local 实现
- [x] 接入 MinIO / S3 实现
- [x] HTML 快照、上传文件、报告导出件统一走 ArtifactStorage
- [x] SourceArtifact 记录 object key、sha256、content type 和 size
- [x] 增加对象存储失败降级策略
- [x] 增加快照读取 API 或内部服务

6.4 MVP 说明：真实采集路径（collection）与报告导出（routes）本就走 ArtifactStorage 并记录元数据；本轮补齐 demo 播种路径——`write_demo_source_snapshot` 统一写入 HTML 快照到存储（object key 与真实路径同为 `snapshots/{task_id}/{source_id}.html`），SourceArtifact 的 sha256/size 记录真实快照字节，离线 demo 模式下证据 → 快照溯源链路可用（新增测试 `test_stage_six_demo_sources_persist_snapshots_in_artifact_storage`）。快照读取走 `GET /v1/sources/{id}/snapshot`，按 SourceArtifact.object_key 读取，缺失时稳定降级。"上传文件"当前产品无上传入口（来源仅 URL / 手动 URL），该项按 N/A 处理。

6.4 补充（快照原文读取 API，为将来知识库按引用取回文件预留）：新增 `GET /v1/sources/{source_id}/snapshot/raw`，经 ArtifactStorage 返回快照原始字节，响应头携带 `X-Artifact-Object-Key` / `X-Artifact-Sha256` / `X-Artifact-Size`，调用方可对字节做 sha256 校验；来源不存在 / 无 artifact 记录 / 文件缺失分别返回稳定错误码（source_not_found / snapshot_not_found / snapshot_file_missing）。配合报告导出接口（POST `/reports/{id}/export`），外部系统（如个人知识库）可用 `object_key + sha256` 稳定引用并取回全部产物，存储后端切换（Local/MinIO/Fallback）对调用方透明。新增 2 条测试覆盖正常读取与三种 404 语义；顺带修复测试封闭性问题——直接构造 `Settings()` 会读取 backend/.env，涉及"无 Key"假设的测试显式传空 key，避免本机配置了 TAVILY_API_KEY 后测试发起真实外网搜索。

### 6.5 Elasticsearch

- [x] 建立 Evidence 索引结构
- [x] 建立 Source 索引结构
- [x] 实现资料索引服务
- [x] 实现资料检索服务
- [x] 支持按 task、competitor、dimension、source_type 过滤
- [x] 支持索引重建
- [x] 明确 ES 只做可重建检索层，MySQL 仍是事实库

### 6.6 Docker Compose 和可部署版本

- [x] 完善 Docker Compose
- [x] 增加后端容器
- [x] 增加前端容器
- [x] 增加 MySQL、Redis、Elasticsearch、MinIO 服务
- [x] 增加健康检查
- [x] 增加日志收集
- [x] 增加基础监控指标
- [x] 完成一键启动演示脚本

### 阶段 6 验收标准

- [ ] Docker Compose 可以启动前端、后端、MySQL、Redis、Celery、MinIO、Elasticsearch
- [ ] 使用 MySQL 和 Celery 时，完整研究流程能跑通
- [ ] HTML 快照和报告导出件可以进入 MinIO / S3
- [ ] Evidence 可以进入 Elasticsearch 并支持检索
- [ ] MySQL 是唯一事实库，ES 和对象存储都可以从事实数据重建

---

## 十、阶段 7：产品体验完善（工作流稳定后的产品化）

### 目标

让 MVP 从“能跑”提升到“可用、易理解、可持续使用”。

本阶段优先增强用户围绕“研究任务”的真实工作流，而不是做泛平台功能。前端应突出证据、结论、审核和报告，而不是做营销式首页。

### 任务

### 7.1 任务创建和研究范围

- [x] 优化研究任务创建表单
- [x] 支持竞品、维度、来源偏好、时间范围、报告深度的结构化输入
- [x] 增加手动 URL 输入区，方便无搜索 API Key 时测试真实采集
- [x] 增加任务确认页的范围预览
- [x] 增加预算提示：最大搜索轮次、候选来源数、运行时长

7.1 MVP 说明：
- 任务确认页已新增手动来源 URL 输入区，支持换行、空格或逗号分隔，并只保留去重后的 http / https URL。
- 手动 URL 会合并进 `source_preferences` 随任务创建提交，后端现有采集链路可从来源偏好中提取 URL。
- 右侧研究设置已增加范围预览，展示竞品数量、维度数量和手动 URL 数量。
- 预算提示继续展示搜索轮次、候选来源和预计分钟；候选来源数会至少覆盖手动 URL 数量。
- 结构化任务创建已补齐可编辑任务标题、报告深度、时间范围、输出目标，以及竞品 / 维度 / 来源偏好的新增和去重；前端通过统一 `buildStructuredTaskPayload` 构造后端创建参数，保持现有 API 合约不变。

### 7.2 任务列表和详情

- [x] 增加研究任务列表
- [x] 增加任务搜索和筛选
- [x] 增加任务详情页
- [x] 增加失败任务重试
- [x] 增加任务取消
- [x] 增加任务状态原因展示
- [x] 区分当前 run 和历史 run

7.2 MVP 说明：
- “我的调研”页面已增加任务搜索框和状态筛选，调用后端列表接口的 `q/status` 参数。
- 任务列表展示状态原因、证据数、Claim 数、引用覆盖率，并在失败 / 已取消任务上提供重试入口。
- 任务详情面板展示当前任务状态说明、异常原因、当前 run、当前阶段、证据 / Claim 统计和报告入口。
- 前端已接入取消接口，可从列表或详情取消仍可取消的任务。
- 后端任务详情响应新增 `runs` 数组，前端按当前 run 与历史 run 分开展示。

### 7.3 研究过程时间线

- [x] 基于 Stage 5 节点事件展示研究过程时间线
- [x] 展示每个节点的开始、成功、失败、重试状态
- [x] 展示节点耗时和关键输出摘要
- [x] 失败节点可展示错误信息
- [x] 支持从失败节点继续执行的操作入口

7.3 MVP 说明：
- 后端新增 `POST /v1/research-tasks/{task_id}/resume`，仅允许失败任务复用当前失败 run 的最近成功 checkpoint 继续执行。
- inline 模式会立即调用 `run_research_workflow(..., resume=True)`；Celery 模式会用同一个 run 入队并传递 `resume=True`。
- 前端任务列表、任务详情和失败时间线节点已新增“继续执行”入口，并与“重试”（新建 run 从头执行）区分。

### 7.4 证据和来源体验

- [x] 增加证据详情查看
- [x] 增加来源跳转
- [x] 展示 Source 原始 URL、canonical URL、publisher、retrieved_at
- [x] 展示 Evidence locator、quality_score、extraction_method
- [x] 支持按竞品、维度、来源类型筛选 Evidence
- [x] 支持查看 HTML 快照或快照摘要

7.4A / 7.4B MVP 说明：

- 任务详情接口已支持 `evidence_competitor`、`evidence_dimension`、`evidence_source_type` 三个可选筛选参数；竞品 / 维度筛选通过 Claim-Evidence 关联定位 Evidence，来源类型筛选通过 Source.source_type 完成。
- 前端运行页证据库已增加来源类型、竞品、维度筛选控件，并在任务详情刷新和轮询时保留当前筛选。
- 后端已新增 `GET /v1/sources/{source_id}/snapshot`，可读取本地 HTML 快照并返回摘要；快照文件缺失时返回稳定的不可用状态。
- 证据浮层和报告引用抽屉已展示 locator、可信度、extraction_method，并支持按需查看快照摘要。

### 7.5 Claim 审核体验

- [x] 增加结论审核交互
- [x] 支持批量接受低风险 Claim
- [x] 支持排除 Claim 并填写原因
- [x] 支持标记不确定并进入风险章节
- [x] 展示 Claim 绑定的 Evidence 列表
- [x] 展示 Claim 的置信度、引用覆盖率和冲突状态

7.5A MVP 说明：

- 前端审核页已将待审核 Claim 转成独立 ReviewItem 视图模型，展示状态、置信度、引用覆盖率和绑定 Evidence 摘要。
- 审核页新增了可聚焦的 Claim 详情面板，点击任一风险项即可查看更完整的证据摘要、审核原因和处理动作，减少在列表里来回切换。
- 每条审核卡片支持填写审核原因；提交时优先使用用户输入，未填写则使用系统建议作为兜底原因。
- 绑定 Evidence 以可点击条目展示，可复用现有 Evidence 详情浮层查看证据上下文。

7.5B MVP 说明：
- 审核页已新增“批量接受”入口，自动筛选已验证、未审核、进入报告、置信度和引用覆盖率均不低于 80% 且绑定 Evidence 的低风险 Claim。
- 批量接受复用现有单条 Claim 审核接口，逐条提交 `accept` 决策并写入统一原因，完成后刷新任务详情和任务列表。
### 7.6 报告和导出

- [x] 增加报告版本历史
- [x] 增加报告重新生成
- [x] 支持 Markdown 导出
- [x] 支持 PDF 导出
- [x] 支持 DOCX 导出
- [x] 展示引用覆盖率
- [x] 展示每个章节引用的 Evidence
- [x] 支持审核后生成新版本报告

7.6A MVP 说明：
- 后端新增 `POST /v1/research-tasks/{task_id}/reports/regenerate`，在风险 Claim 已处理完毕后基于当前审核状态生成下一版报告。
- 报告再生成复用现有版本递增能力，不覆盖旧报告；若仍有未处理风险 Claim，会返回 409，避免生成未审完的最终报告。
- 前端报告页版本历史已展示生成原因、生成时间和引用覆盖率，并支持手动重新生成后自动选中新版本。

7.6B MVP 说明：
- 后端 `ReportSectionOut` 已新增章节级 `evidence` 数组，报告生成时会将各章节关联 Evidence 写入版本快照。
- 前端报告页会在每个章节正文下展示 Evidence 摘录、来源、质量分和关联 Claim 数，旧报告没有快照时保持空数组兼容。

### 7.7 竞品库和用户隔离

- [x] 增加竞品对象管理
- [x] 支持保存竞品官网、文档、定价页等常用来源
- [x] 支持复用历史竞品研究结果
- [ ] 增加权限和用户隔离
- [x] 增加组织 / workspace 概念

7.7A MVP 说明：
- 后端新增 `CompetitorProfile` 持久化模型和 `POST /v1/competitors`、`GET /v1/competitors` 接口，支持保存官网、文档、定价页等常用来源。
- 竞品列表会基于任务 scope、Claim subject 和 Report 聚合关联任务数、已验证 Claim、风险 Claim 与报告数；当前先使用 `default` workspace 字段，为后续用户隔离保留结构。
- 前端竞品库已从静态列表切换为 API-backed rows，接口不可用或暂无 Profile 时保留原有演示数据兜底。

7.7B MVP 说明：
- 创建研究任务时会按竞品名称匹配 `CompetitorProfile`，自动将已保存官网、文档、定价页等来源合并进 `scope.source_preferences`，并去重保留用户手动 URL 优先级。
- 任务 scope 会记录 `competitor_profile_reuse`，用于说明复用了哪些 Profile 和来源；前端确认页已展示竞品库复用来源提示。

7.7C MVP 说明：
- `ResearchTask` 已新增 `workspace_id`，创建任务时可传入 `workspace_id` 和 `created_by`，列表接口支持按 workspace / 用户过滤。
- 当前是数据边界和查询隔离，尚未接入登录态、成员关系和强制鉴权，因此“权限和用户隔离”继续保留到后续阶段。

### 阶段 7 验收标准

- [x] 用户可以结构化创建研究任务，而不只输入长 prompt
- [x] 用户可以理解每个研究节点发生了什么
- [x] 用户可以从证据追溯到来源和快照
- [x] 用户可以审核 Claim 并触发报告版本更新
- [x] 用户可以导出 Markdown / PDF / DOCX 报告
- [x] 失败、取消、重试都有清晰入口和状态反馈

7.8A MVP 说明：
- 前端任务详情已新增恢复反馈提示，会针对失败、可继续执行、已取消和运行中任务给出明确下一步动作。
- `researchTasks` 已新增 `buildTaskRecoveryFeedback` 测试模型，复用现有继续执行、重试和取消接口，不改变后端状态流转。

7.9 MVP 说明（研究时间线可读性）：
- `researchTimeline` 已为每个 LangGraph 节点补充中文说明文案（该节点在做什么），时间线节点卡片在标签和状态之外展示节点说明，用户可以理解每个研究节点发生了什么。
- 修复了 `buildAuditEvents` 事件标签乱码，并建立准确的事件类型中文标签映射：`node.*` 事件按节点名展示（如“网页抓取”），业务事件按类型展示（规划/检索/来源/证据/结论/审核/报告/运行/任务），未知类型回退原始 type。
- App.vue 移除了本地重复的 `eventTypeLabel`，统一消费 `researchTimeline` 的准确标签，活动流不再把 `node.*`、`run.failed` 等事件统一误标为“质检”。

---

## 十一、阶段 8：测试与交付（持续贯穿，版本发布前收口）

### 目标

确保系统具备稳定演示和后续迭代基础。

### 任务

### 8.1 后端测试

- [ ] 后端单元测试
- [x] API 合约测试
- [ ] 数据库测试
- [ ] 工作流节点测试
- [ ] LangGraph 集成测试
- [x] Celery 任务测试
- [x] LLM 输出校验测试
- [x] 搜索 / 抓取 / 解析失败场景测试
- [x] checkpoint 恢复测试
- [x] 失败重试测试
- [x] 报告导出测试

### 8.2 前端测试

- [ ] 前端组件测试
- [x] 前端构建测试
- [x] API 失败状态测试
- [x] 空数据状态测试
- [x] 时间线事件展示测试
- [x] 任务恢复反馈测试
- [x] Claim 审核交互测试
- [x] 报告版本展示测试
- [x] 报告章节证据展示测试
- [x] 竞品库列表映射测试
- [x] 竞品库来源复用提示测试

8.2 MVP 说明（空数据状态与 API 失败状态）：
- 新增 `researchStates.test.mjs`（16 条测试）：覆盖时间线空事件（工作台摘要“尚未开始”）、证据墙空证据与无绑定 Claim 行、审核列表空 Claim、任务摘要全空详情、未知任务状态回落草稿态但保留原始状态值。
- API 失败状态覆盖：网络异常（fetch reject）原样抛出、500 空 body 回落 `API request failed: 500`、422 无 message 时取 error code、FastAPI `detail` 格式错误（无 error 包装）回落状态码文案。
- 修复两处边界 bug：`buildResearchTimeline(null)` 与 `filterEvidenceViewModels(null)` 此前抛 TypeError，现安全返回空数组。
- 测试基线更新：前端 17 个测试文件 90 条全过，构建通过。

### 8.3 端到端验收

- [x] 端到端流程测试
- [x] 无 Tavily API Key 的手动 URL 流程测试
- [x] 无 LLM API Key 的规则 fallback 流程测试
- [x] 有 Tavily + 有 LLM API Key 的真实流程测试（依赖真实 API Key 和外网，保留为人工验收项）
- [x] Celery 异步流程测试
- [x] 失败恢复流程测试
- [x] 人工审核后重生成报告流程测试

v1.0.0 版本验收记录（2026-08-26，真实 Key 链路）：删除本地 DB 与 storage 后按《启动指南》从零启动后端（8000）+ 前端（5173），health 检查通过；创建"调研 Cursor 的企业版定价与协作管控能力"任务（无手动 URL，走真实 Tavily 搜索），任务 completed：4 个真实来源（含 cursor.com 官方博客）、12 条证据、3 条 Claim（0 风险）、报告 v1 引用覆盖率 100%；事件流完整（11 个节点全部 started/succeeded），真实运行中出现 1 次 source.parse_skipped（低质量正文跳过、任务不中断，韧性机制实战验证）；三种格式导出（markdown/pdf/docx）全部 200；快照原文 API 在真实来源上验证（321KB HTML，sha256 校验一致）。

8.3 MVP 说明（离线端到端验收）：
- 新增 `test_stage_eight_manual_url_flow_without_tavily_key`：无 Tavily / 无 LLM Key 时，通过 `source_preferences` 手动 URL 走完 创建任务 → confirm → 采集（mock HttpPageFetcher）→ 证据 → Claim → 报告 全链路，并断言 search.started / source.found / evidence.created 事件。
- 新增 `test_stage_eight_rule_based_fallback_flow_without_llm_key`：无 LLM Key 时规则抽取的每条 Claim 都绑定 Evidence、claim_type 按关键词分类正确、报告引用覆盖率大于 0，且 Markdown 导出返回 artifact object key。
- 高质量手动来源产出的 Claim 无风险时 review gate 直接放行（任务 completed），与风险 Claim 阻塞（waiting_review）行为并存。
- Celery 异步流程已有 mock broker 的离线验证：confirm 入队优先级、worker checkpoint 自动恢复、health 配置上报。
- 测试基线：后端 87 passed（两种 pytest 调用路径均修复 Windows 临时目录权限问题，backend/pytest.ini 同步固化 basetemp）。

8.1 MVP 说明（LLM 输出校验与失败重试）：
- LLM 输出校验新增 6 条测试：非 JSON 文本报 `claim_json_not_found`；完全未闭合 JSON 报 `claim_json_not_closed`，截断 JSON 与 fenced 块报 `invalid_claim_json`；顶层标量 payload 报 `claim_payload_must_be_object`，顶层数组会被包成 claims 并过滤非对象元素；`claims` 非数组报 `claim_payload_claims_must_be_array`。
- 新增 LLM 幻觉 evidence_id 过滤测试：LLM 返回不存在 evidence_id 的 Claim 会被 `extract_and_store_claims` 过滤，只保留绑定真实 Evidence 的结论，验证“证据链不能退化”约束。
- 新增 LLM 运行时不可用（LLMUnavailable）回退测试：上游连接失败时回退规则抽取并继续产出绑定 Evidence 的 Claim，而非任务失败。
- 失败重试新增 2 条测试：报告生成重试耗尽时抛 `report_generation_failed`、事件 severity 按 warning→warning→error 递进、不残留半成品 Report；HttpPageFetcher 重试耗尽抛出最后一次 httpx 错误且调用次数为 max_retries+1。
- 测试基线更新：后端 95 passed。

### 8.4 文档和交付

- [x] 编写开发环境启动文档
- [x] 编写接口文档
- [x] 编写工作流节点文档
- [x] 编写 MVP 演示脚本
- [x] 编写部署文档
- [x] 编写常见故障排查文档
- [x] 清理临时数据库和日志文件
- [x] 完成一次完整版本验收

8.4 收口说明：MVP 演示脚本见 docs/MVP演示脚本.md（六幕演示流程 + 验收核对单）；完整版本验收已于 2026-08-26 执行（记录见 8.3 验收记录），干净环境按文档启动 + 真实 Key 全链路通过。

8.4 MVP 说明（交付文档与清理）：
- 新增 docs/ 交付文档（按主题分文件）：启动指南（三种模式：本地开发 / Docker Compose / Celery 异步，含无 Key 最小验证路径）、API 接口（25 个端点速查 + 状态机 + 调用示例）、工作流节点（11 个 LangGraph 节点职责、checkpoint 恢复机制、事件类型速查）、部署指南（compose 编排说明 + 生产前必办清单）、排障手册（按现象索引）。
- 已知限制已写入部署指南（无鉴权、默认密码、镜像固化 API 地址等）；生产化差距单列，不在 MVP 范围内。
- 执行 cleanup_dev_artifacts.py 清理本地临时产物（uvicorn/vite 日志、verda_dev.db、verda_stage3_smoke.db、dist、pytest 缓存），源码/.env/虚拟环境不受影响。
- 清理后回归：后端 95 passed。

### 阶段 8 验收标准

- [x] 新环境可以按文档启动
- [x] 后端测试、前端构建、核心端到端流程通过
- [x] 演示脚本可以稳定复现创建任务、执行研究、审核 Claim、导出报告
- [x] 已知限制被写入 README 或发布说明

---

## 十二、当前执行顺序

当前已经完成从 0 到 4B 的 MVP 能力建设。后续不要再按“大阶段并行推进”，而是按以下开发顺序收敛：

### P0：当前基线保护

1. [x] 确认项目版本管理方式，建议初始化 git 或建立明确备份
2. [x] 跑通后端测试
3. [x] 跑通前端构建
4. [x] 补一条完整研究流程回归测试
5. [x] 固化当前 API 合约

### P1：LangGraph 最小工作流

6. [x] 新增 `backend/app/workflows/`
7. [x] 定义 `ResearchWorkflowState`
8. [x] 实现 `run_research_workflow(db, run_id)`
9. [x] 将现有 `simulate_research_run` 内部切到 workflow
10. [x] 保持 inline / celery 两种模式可用
11. [x] 跑通完整任务闭环

### P2：节点事件和拆分

12. [x] 定义节点生命周期事件规范
13. [x] 拆出任务理解、采集、Claim 抽取、报告、审核节点
14. [x] 每个节点记录输入摘要、输出摘要、耗时和错误
15. [x] 独立 `verify_claims` 节点，检查引用完整性、置信度、低证据覆盖和冲突风险
16. [x] 前端时间线消费新的节点事件

### P3：视频目标体验闭环

17. [x] 对话式任务入口：输入调研需求后生成 2-4 个澄清问题
18. [x] 权重确认页：支持产品类别、研究重点、来源偏好、时间范围和补充要求
19. [x] 研究工作台：用节点事件展示实时研究流、阶段进度、证据数量和失败原因
20. [x] 证据墙：展示网页、新闻、社交舆情等证据卡片，支持按来源 / 竞品 / 维度筛选
21. [x] 证据溯源：点击 Evidence 可查看原始 URL、canonical URL、publisher、locator、HTML 快照或摘要
22. [x] Claim 质量判断：展示置信度、引用覆盖率、冲突状态和绑定 Evidence
23. [x] 审核后报告更新：用户接受、排除或标记不确定后可生成新版本报告

P3-17/18 MVP 说明：
- 首页输入研究需求后，先进入“确认研究计划”，不会立刻创建后端任务；用户确认后才真正创建任务并启动研究。
- 前端新增规则版 `researchClarifier`，可以生成 2-4 个 Agent 追问、研究权重、来源偏好和预算提示。
- 用户可编辑追问答案、调整权重滑杆、删除来源偏好；确认内容会拼接进后端收到的 prompt，让现有研究链路先吃到权重上下文。
- 当前是前端规则版澄清，不是后端 LLM 动态追问；后续可替换为真实 Agent 规划接口。

P3-20 MVP 说明：
- 运行页右侧“证据库”已升级为证据墙，展示当前筛选后的证据数量、高质量证据数和来源类型数。
- `researchEvidence` 已新增证据墙视图模型，会把 Evidence 绑定到对应 Claim 的竞品、维度和标签，并按质量分生成高 / 中 / 低质量视觉状态。
- 证据墙支持按来源类型、竞品和维度筛选；点击证据卡片继续复用现有证据详情浮层和溯源能力。

P3-21 MVP 说明：
- 新增 `researchEvidence` 证据视图模型，将 `EvidenceOut.source` 和 `EvidenceOut.locator` 转成前端可展示的溯源字段。
- 运行页证据浮层和报告页引用抽屉已展示原始 URL、canonical URL、publisher、retrieved_at、locator、可信度和快照提示。
- 已提供“打开来源”按钮，可跳转到原始 URL 或 canonical URL。
- 已接入 `GET /v1/sources/{source_id}/snapshot`，证据详情可按需读取快照摘要；前端统一处理读取中、不可用、失败和重新读取状态。

P3-22 MVP 说明：
- 新增 `buildClaimQualityJudgement` 质量判断模型，统一输出风险级别、置信度文本、引用覆盖率、状态文本、Evidence 数量和可读风险标签。
- 运行页 Claim 卡片已展示质量判断结果，并继续支持点击绑定 Evidence 跳转到证据详情。

P3-23 MVP 说明：
- 新增 `buildPostReviewReportUpdateState` 报告更新状态模型，用于识别审核后生成的最新报告版本。
- 报告页已展示审核后新版本提示，用户查看旧版本时可一键切换到最新审核后报告。

### P4：checkpoint、恢复和人工审核后继续

24. [x] 保存节点级 checkpoint
25. [x] 支持失败任务从最近成功节点恢复
26. [x] 支持人工审核后重生成报告
27. [x] 支持报告版本递增
28. [x] 支持任务取消和失败重试

### P5：真实数据源和舆情扩展

29. [x] 抽象 `SocialListeningAdapter`，统一社交舆情来源接入
30. [x] 优先接入 1-2 个稳定、合规、无需复杂登录的舆情来源
31. [x] 将舆情内容标准化为 Source / Evidence，并标记 `source_type`
32. [x] 支持舆情情绪、热度、发布时间和互动指标字段
33. [x] 明确平台 API、登录、robots 和合规边界

### P6：异步和基础设施

34. [x] Celery 切换到 workflow 真实异步执行
35. [ ] 引入 MySQL
36. [ ] 引入 MinIO / S3
37. [ ] 引入 Elasticsearch
38. [ ] 完善 Docker Compose 一键启动

### P7：产品体验和交付

39. [x] 优化结构化任务创建
40. [x] 优化研究时间线、证据详情和 Claim 审核
41. [x] 增加报告版本历史和 PDF / DOCX 导出
42. [ ] 增加竞品库和用户隔离（暂缓：当前阶段仅验证主链路可行性，不投放多人使用；现有 workspace_id 数据边界已为将来接入认证预留兼容结构，届时补充用户模块 + 请求鉴权 + 数据归属即可）
43. [ ] 完成端到端验收和部署文档

---

## 十三、当前里程碑

### M0：架构和后端骨架

状态：已完成。

### M1：前后端 MVP 闭环

状态：已完成。

验收标准：可以从前端创建任务、启动研究、查看证据和报告。

### M2：真实数据采集

状态：3A MVP 已完成。

验收标准：研究结果来自真实搜索和网页内容。

当前说明：已支持 Tavily Search Adapter、手动 URL fallback、真实网页抓取、本地 HTML 快照、Trafilatura 正文解析、Source / Evidence 入库、robots 检查、重试、限速和低质量正文过滤。MinIO / S3 尚未接入，当前使用本地快照存储。

### M3：真实 Agent 分析

状态：4B MVP 已完成。

验收标准：Agent 可以完成结构化抽取、引用绑定和报告生成。

当前说明：已支持 OpenAI-compatible LLM Provider；无 LLM API Key 时使用规则抽取 fallback；Claim 输出经过 Schema 校验后入库，并强制绑定 Evidence；可生成结构化报告草稿。已补齐异常输出修复、报告模板、报告生成失败重试和人工审核闭环。

### M4：可部署版本

状态：待开始。启动条件是 Stage 5 的 LangGraph 最小工作流已经跑通。

验收标准：通过 Docker Compose 启动完整服务，并完成核心流程测试。

### M5：LangGraph 工作流版本

状态：下一阶段优先启动。

验收标准：完整研究任务由 LangGraph workflow 执行，节点事件完整写入，失败节点可定位，人工审核后可以继续生成报告。

### M6：可恢复长任务版本

状态：待 M5 完成后启动。

验收标准：任务支持 checkpoint、失败恢复、节点重试、取消和报告版本递增。

### M7：可部署竞品研究 Agent

状态：待 M6 完成后启动。

验收标准：Docker Compose 启动完整服务，MySQL 作为事实库，Redis / Celery 执行异步任务，MinIO / S3 保存快照和导出件，Elasticsearch 支持 Evidence 检索。

---

## 十四、后续设计约束

1. **证据优先**：报告中的事实性结论必须能追溯到 Claim，Claim 必须绑定 Evidence，Evidence 必须能追溯到 Source。
2. **MySQL 是事实库**：Search、ES、对象存储都不是事实来源，只是可重建的辅助系统。
3. **前端以任务流为中心**：优先做好创建任务、查看进度、审阅证据、审核结论、导出报告。
4. **工作流先稳定再扩展 Agent 能力**：不要过早加入复杂多 Agent、自主规划、IM 集成或通用沙盒。
5. **每个节点都要可测试**：节点输入、输出、失败和重试策略都需要测试覆盖。
6. **本地开发要能离线跑**：没有 Tavily API Key 和 LLM API Key 时，仍应保留手动 URL 和规则 fallback。
7. **基础设施可替换**：SQLite / LocalArtifactStorage / inline workflow 是本地默认；MySQL / MinIO / Celery 是部署增强，不应破坏本地体验。
