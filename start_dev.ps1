# 一键启动本地开发环境：后端 API + Celery Worker + 前端
# 用法：
#   .\start_dev.ps1              # 启动全部（API + Worker + 前端）
#   .\start_dev.ps1 api          # 只启动后端 API
#   .\start_dev.ps1 worker       # 只启动 Celery Worker
#   .\start_dev.ps1 frontend     # 只启动前端
#   .\start_dev.ps1 api worker   # 组合启动
# 依赖：backend/.venv（首次需 python -m venv .venv 并 pip install -r requirements.txt）
#       frontend/node_modules（首次需 npm install）
# 中间件（MySQL/Redis/ES）由虚拟机 Docker 提供，需保证 192.168.150.101 可达。

param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Targets
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'

# 默认启动全部
if (-not $Targets) { $Targets = @('api', 'worker', 'frontend') }

function Test-PathSafe([string]$Path, [string]$Hint) {
    if (-not (Test-Path $Path)) {
        Write-Host "[缺失] $Path" -ForegroundColor Red
        Write-Host "  -> $Hint" -ForegroundColor Yellow
        exit 1
    }
}

function Start-Api {
    Test-PathSafe "$Backend\.venv\Scripts\python.exe" "先在 backend 目录执行: python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
    Write-Host "`n[1/3] 启动后端 API  http://127.0.0.1:8000  (文档 /docs)" -ForegroundColor Cyan
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command",
        "cd '$Backend'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
}

function Start-Worker {
    Test-PathSafe "$Backend\.venv\Scripts\celery.exe" "先安装依赖: .venv\Scripts\pip install -r requirements.txt"
    Write-Host "`n[2/3] 启动 Celery Worker (队列: research)" -ForegroundColor Cyan
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command",
        "cd '$Backend'; .\.venv\Scripts\celery.exe -A app.workers.celery_app.celery_app worker -Q research --loglevel=info -P solo"
}

function Start-Frontend {
    Test-PathSafe "$Frontend\node_modules" "先在 frontend 目录执行: npm install"
    Write-Host "`n[3/3] 启动前端  http://localhost:5173" -ForegroundColor Cyan
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command",
        "cd '$Frontend'; npm run dev"
}

foreach ($target in $Targets) {
    switch ($target.ToLower()) {
        'api'      { Start-Api }
        'worker'   { Start-Worker }
        'frontend' { Start-Frontend }
        default    { Write-Host "未知目标: $target（可选 api / worker / frontend）" -ForegroundColor Red; exit 1 }
    }
}

Write-Host @"

启动完成，各服务在独立窗口运行，关闭对应窗口即停止服务。

  后端 API   http://127.0.0.1:8000      健康检查 /v1/health
  API 文档   http://127.0.0.1:8000/docs
  前端       http://localhost:5173

提示：
  - AUTH_MODE 默认 strict，首次使用先在前端注册账号
  - 中间件不可达时后端仍可启动（降级本地存储/离线链路），仅任务执行受影响
"@ -ForegroundColor Green
