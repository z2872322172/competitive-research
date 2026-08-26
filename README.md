# 智能竞品分析 Agent

这是一个面向竞品研究场景的智能分析 Agent MVP。目标演示链路是：创建研究任务、确认任务、执行研究流程、查看执行进度、查看证据、审核结论、查看并导出分析报告。

当前项目已经完成前后端 MVP 闭环，并推进到真实信息采集、结构化 Claim 分析和人工审核闭环。

## 当前能力

- 前端：Vue 应用已接入任务创建、任务确认、任务详情、事件轮询、Evidence / Claim / Report 展示、Claim 审阅、继续研究和 Markdown 报告导出。
- 后端：FastAPI 提供研究任务、事件、证据、结论、报告和导出 API。
- 数据：MVP 默认使用 SQLite，已建立 ResearchTask、TaskRun、ResearchEvent、Source、Evidence、Claim、Report 等核心模型。
- 采集：支持 Tavily Search Adapter；无搜索 API Key 时可从 prompt 或 `source_preferences` 中提取手动 URL。
- 抓取：支持真实网页抓取、本地 HTML 快照、Trafilatura 正文解析、robots 检查、失败重试、域名限速和低质量正文过滤。
- 分析：支持 OpenAI-compatible LLM Provider；无 LLM API Key 时使用规则抽取 fallback；Claim 入库前进行 Schema 校验，并强制绑定 Evidence。
- 报告：支持结构化 Markdown 报告模板、引用覆盖统计、报告生成失败重试、人工审阅后交付，并通过 API 导出。

## 项目结构

```text
competitive-research/
  backend/     FastAPI API、SQLAlchemy 模型、采集/解析/分析服务、Celery 入口、测试
  frontend/    Vue 前端应用
  skills/      项目辅助技能和提示词
  智能竞品分析Agent_MVP开发待办清单.md
  智能竞品分析Agent_PRD.md
  智能竞品分析Agent_产品原型设计.md
  智能竞品分析Agent_后端架构与开发计划.md
```

## 后端本地启动

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

默认 `TASK_MODE=inline`，研究流程会在 API 进程内同步执行，适合本地演示。需要 Redis 和 Celery Worker 时可切换为 `TASK_MODE=celery`。

```powershell
celery -A app.workers.celery_app.celery_app worker --loglevel=info
```

## 前端本地启动

```powershell
cd frontend
npm install
npm run dev
```

前端默认通过 Vite 启动，后端 API 地址由前端 API 封装中的配置读取。

## 可选环境变量

真实搜索：

```powershell
$env:TAVILY_API_KEY = "tvly-..."
$env:SEARCH_PROVIDER = "tavily"
$env:SEARCH_MAX_RESULTS = "5"
$env:FETCH_RESPECT_ROBOTS = "true"
```

真实 LLM 抽取：

```powershell
$env:LLM_PROVIDER = "openai"
$env:LLM_BASE_URL = "https://api.openai.com/v1"
$env:LLM_MODEL = "chat-latest"
$env:OPENAI_API_KEY = "sk-..."
```

没有 `TAVILY_API_KEY` 时，系统会保持 demo fallback；也可以在 prompt 或 `source_preferences` 中放入 `https://...` URL 来测试真实抓取和解析路径。没有 LLM API Key 时，系统使用规则抽取 fallback，保证本地测试和演示可运行。

## 测试

```powershell
.\backend\.venv\Scripts\python.exe -m pytest
```

当前测试覆盖 API 合约、完整研究流程回归、任务状态机、数据模型约束、真实采集离线路径、网页解析 fallback、robots / retry 行为、Stage 4A 规则 Claim 抽取和 Evidence 绑定，以及 Stage 4B LLM 输出修复、报告模板和报告失败重试。根目录 `pytest.ini` 已固定 `backend` 为 Python import path，便于后续 LangGraph 改造前后使用同一条基线命令。

## 开发环境清理

先 dry-run 查看会被清理的本地临时产物：

```powershell
.\backend\.venv\Scripts\python.exe backend\scripts\cleanup_dev_artifacts.py
```

确认无误后再显式执行清理：

```powershell
.\backend\.venv\Scripts\python.exe backend\scripts\cleanup_dev_artifacts.py --apply
```

当前清理范围只覆盖本地数据库、日志、pytest 缓存和前端构建产物，不会删除源码、`.env`、虚拟环境或 `node_modules`。

## 下一步路线

1. 引入 LangGraph，将当前线性研究流程拆成可观察、可恢复的 Agent 节点。
2. 升级基础设施：MySQL、Elasticsearch、MinIO / S3、容器化和健康检查。
3. 补齐产品化能力：报告版本历史、任务取消、PDF / DOCX 导出和用户隔离。

## Docker Compose 启动

根目录已提供一键编排：

```powershell
docker compose up --build
```

也可以直接运行 `start_demo.ps1`。

默认会启动 `backend`、`worker`、`frontend`，以及 MySQL、Redis、Elasticsearch、MinIO。
前端默认访问 `http://localhost:5173`，后端默认访问 `http://localhost:8000/v1`。
