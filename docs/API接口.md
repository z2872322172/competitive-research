# API 接口文档

所有接口挂在 `/v1` 前缀下，完整定义见 `backend/app/api/routes.py` 与 `backend/app/schemas.py`（本档为索引速查）。

## 通用约定

- **认证**：当前无登录鉴权（MVP 阶段，见待办 P7-42）。请求头 `X-Workspace-Id` / `X-User-Id` 用于工作区数据边界，后端不校验真实性。
- **错误格式**：非 2xx 返回 `{ "error": { "code", "message" } }`；请求体校验失败为 FastAPI 默认 `detail` 格式。
- **事件流**：任务事件可通过轮询 `GET /events` 或 SSE `GET /events/stream` 获取。

## 健康与监控

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 服务健康状态 |
| GET | `/worker/health` | Celery worker 状态（inline 模式下报告 inline） |
| GET | `/metrics` | 监控指标 |

## 研究任务

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/research-tasks` | 创建任务（prompt / competitors / dimensions / source_preferences） |
| GET | `/research-tasks` | 任务列表，支持 status、q、workspace_id、分页 |
| GET | `/research-tasks/{task_id}` | 任务详情（task + runs + sources + evidence + claims + reports） |
| POST | `/research-tasks/{task_id}/confirm` | 确认任务并触发首次研究（`?background=true` 走 Celery） |
| POST | `/research-tasks/{task_id}/runs` | 重新运行（新 run） |
| POST | `/research-tasks/{task_id}/resume` | 从 checkpoint 恢复失败的 run |
| POST | `/research-tasks/{task_id}/cancel` | 取消运行中的任务 |
| POST | `/research-tasks/{task_id}/reports/regenerate` | 审核后重生成报告（新版本） |
| GET | `/research-tasks/{task_id}/events` | 事件列表（时间线数据源） |
| GET | `/research-tasks/{task_id}/events/stream` | SSE 实时事件流 |

## 来源与证据

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/sources/{source_id}` | 来源详情 |
| GET | `/sources/{source_id}/snapshot` | HTML 快照内容（证据溯源） |
| GET | `/sources/{source_id}/snapshot/raw` | 快照原始文件字节流；响应头 `X-Artifact-Object-Key` / `X-Artifact-Sha256` / `X-Artifact-Size`，sha256 可校验完整性（知识库/外部系统按引用取回文件的入口） |
| GET | `/evidence/{evidence_id}` | 证据详情（含定位信息） |

## Claim 审核

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/claims/{claim_id}` | Claim 详情 |
| POST | `/claims/{claim_id}/review` | 提交人工审核决策（accept / reject / continue_research） |

## 报告与导出

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/reports/{report_id}` | 报告详情（章节、引用覆盖率、版本） |
| POST | `/reports/{report_id}/export` | 导出，`?format=markdown\|pdf\|docx`；markdown 返回 JSON，pdf/docx 返回文件流；响应头 `X-Artifact-Object-Key` 给出存储对象键 |

## 竞品库与检索

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/competitors` | 创建竞品档案（含来源复用） |
| GET | `/competitors` | 竞品库列表 |
| POST | `/research-tasks/{task_id}/search-index/rebuild` | 重建 ES 检索索引 |
| GET | `/search` | 全文检索来源/证据 |

## 开发辅助

| 方法 | 路径 | 说明 |
|---|---|---|
| DELETE | `/dev/demo-data` | 清空 demo 数据（仅开发环境） |

## 关键状态机

```
任务：draft → confirmed → queued → running → waiting_review → completed
                                        ↘ failed（可 resume / retry）
                                        ↘ canceled
报告：每次 regenerate 生成新版本（version 递增），引用覆盖率 citation_coverage
```

## 常用调用示例

```powershell
# 创建任务（手动 URL，无需搜索 Key）
$body = @{
  prompt = "调研 Cursor 的定价策略"
  competitors = @("Cursor")
  dimensions = @("定价策略")
  source_preferences = @("https://www.cursor.com/pricing")
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/v1/research-tasks -Body $body -ContentType "application/json"

# 确认并执行（inline 模式同步返回 run）
Invoke-RestMethod -Method Post -Uri http://localhost:8000/v1/research-tasks/<task_id>/confirm

# 查看详情与事件
Invoke-RestMethod -Uri http://localhost:8000/v1/research-tasks/<task_id>
Invoke-RestMethod -Uri http://localhost:8000/v1/research-tasks/<task_id>/events
```
