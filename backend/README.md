# Verda Backend MVP

This backend implements the A-plan MVP shell:

```text
FastAPI API + Celery worker + Redis queue + SQLAlchemy fact store
```

The current MVP can run a deterministic demo workflow, and can also use Tavily to collect real web sources and evidence before LLM extraction, Elasticsearch, and MinIO are fully wired.

## Run Locally

Runtime profiles are selected with `APP_ENV`:

| Profile | Default datastore | Default workflow mode | Intended use |
| --- | --- | --- | --- |
| `dev` | `sqlite:///./verda_dev.db` | `inline` | local development and demos without external services |
| `test` | `sqlite:///./verda_test.db` | `inline` | isolated automated tests |
| `prod` | `mysql+pymysql://verda:verda@mysql:3306/verda` | `celery` | Docker/deploy-style integration with MySQL and Redis |

Explicit environment variables such as `DATABASE_URL`, `TASK_MODE`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` override the profile defaults.

For middleware integration, you can either set full URLs or provide host/port pieces:

```powershell
$env:APP_ENV = "prod"

# MySQL: either set DATABASE_URL directly, or fill MYSQL_*.
$env:MYSQL_HOST = "10.10.0.12"
$env:MYSQL_PORT = "3306"
$env:MYSQL_USER = "verda"
$env:MYSQL_PASSWORD = "verda"
$env:MYSQL_DATABASE = "verda"

# Redis / Celery.
$env:REDIS_HOST = "10.10.0.13"
$env:REDIS_PORT = "6379"
$env:REDIS_DB = "0"
$env:CELERY_RESULT_DB = "1"

# Elasticsearch and MinIO are configured now and wired into later Stage 6 services.
$env:ELASTICSEARCH_URL = "http://10.10.0.14:9200"
$env:MINIO_ENDPOINT = "http://10.10.0.15:9000"
$env:MINIO_ACCESS_KEY = "minio"
$env:MINIO_SECRET_KEY = "minio123"
$env:MINIO_BUCKET = "verda-artifacts"
```

```powershell
cd backend
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Default `TASK_MODE=inline` executes the research workflow inside the API process. Set `TASK_MODE=celery` when Redis and a worker are running:

```powershell
$env:TASK_MODE = "celery"
$env:CELERY_BROKER_URL = "redis://localhost:6379/0"
$env:CELERY_RESULT_BACKEND = "redis://localhost:6379/1"
celery -A app.workers.celery_app.celery_app worker -Q research --loglevel=info
```

In Celery mode, `POST /v1/research-tasks/{task_id}/confirm` and `POST /v1/research-tasks/{task_id}/runs` enqueue `research.run` and return the queued run immediately. Both endpoints accept `?priority=0..9`; higher numbers are passed to Celery's Redis priority queue. The service prevents duplicate active runs for the same task before enqueueing.

Use `GET /v1/worker/health` to verify worker configuration from the API process.

The current `docker-compose.yml` starts the integration infrastructure services: MySQL, Redis, Elasticsearch, and MinIO. Full one-command application startup with backend and frontend containers is tracked in Stage 6.6.

## Real Source Collection

Set a Tavily API key to enable the Stage 3A collection path:

```powershell
$env:TAVILY_API_KEY = "tvly-..."
$env:SEARCH_PROVIDER = "tavily"
$env:SEARCH_MAX_RESULTS = "5"
$env:FETCH_RESPECT_ROBOTS = "true"
```

When `TAVILY_API_KEY` is present, confirming a task searches with Tavily, fetches candidate pages with `httpx`, stores local HTML snapshots under `ARTIFACT_STORAGE_DIR`, parses readable text with Trafilatura first and a stdlib fallback, and writes normalized `Source` and `Evidence` rows. The fetcher applies timeout, retry, domain rate limiting, response-size limits, robots.txt checks, and low-quality text filtering. If no key is configured, the API keeps the deterministic demo fallback. You can also include `https://...` URLs in `source_preferences` or the prompt to exercise the fetch/parse path without a search API key.

## Claim Extraction

The Stage 4A path can extract structured `Claim` rows from collected `Evidence`. Without an LLM key, it uses a deterministic rule-based extractor so local tests and demos still run. To enable an OpenAI-compatible model, set:

```powershell
$env:LLM_PROVIDER = "openai"
$env:LLM_BASE_URL = "https://api.openai.com/v1"
$env:LLM_MODEL = "chat-latest"
$env:OPENAI_API_KEY = "sk-..."
```

The LLM response is validated against a JSON Schema before claims are stored. Every stored claim is linked to at least one Evidence row.

## Core API

- `GET /v1/health`
- `GET /v1/worker/health`
- `POST /v1/research-tasks`
- `GET /v1/research-tasks`
- `GET /v1/research-tasks/{task_id}`
- `POST /v1/research-tasks/{task_id}/confirm?priority=5`
- `POST /v1/research-tasks/{task_id}/runs?priority=5`
- `POST /v1/research-tasks/{task_id}/cancel`
- `GET /v1/research-tasks/{task_id}/events`
- `GET /v1/research-tasks/{task_id}/events/stream`
- `GET /v1/evidence/{evidence_id}`
- `GET /v1/claims/{claim_id}`
- `POST /v1/claims/{claim_id}/review`
- `GET /v1/reports/{report_id}`
- `POST /v1/reports/{report_id}/export`

## Demo Request

```powershell
$body = @{
  prompt = "调研 Trae、Cursor、GitHub Copilot、Windsurf 的竞争格局，重点关注产品定位、核心功能、技术能力、定价和用户口碑"
  competitors = @("Trae", "Cursor", "GitHub Copilot", "Windsurf")
  dimensions = @("产品定位", "核心功能", "定价策略", "用户口碑", "技术能力")
} | ConvertTo-Json

$task = Invoke-RestMethod -Method Post -Uri http://localhost:8000/v1/research-tasks -Body $body -ContentType "application/json"
Invoke-RestMethod -Method Post -Uri "http://localhost:8000/v1/research-tasks/$($task.id)/confirm"
Invoke-RestMethod -Uri "http://localhost:8000/v1/research-tasks/$($task.id)"
```

## Tests

```powershell
cd backend
.venv\Scripts\python.exe -m pytest
```
