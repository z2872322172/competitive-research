from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.config import Settings  # noqa: E402


@dataclass(frozen=True)
class CheckResult:
    name: str
    required: bool
    ok: bool
    detail: str


def check_mysql(settings: Settings) -> CheckResult:
    required = settings.database_url.startswith("mysql")
    if not required:
        return CheckResult("mysql", required=False, ok=True, detail="skipped: SQLite mode")
    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            version = connection.execute(text("SELECT VERSION()")).scalar_one()
        engine.dispose()
        return CheckResult("mysql", required=True, ok=True, detail=f"connected: {version}")
    except Exception as exc:
        return CheckResult("mysql", required=True, ok=False, detail=str(exc))


def check_redis(settings: Settings) -> CheckResult:
    required = settings.task_mode == "celery"
    if not required:
        return CheckResult("redis", required=False, ok=True, detail="skipped: inline mode")
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=5, socket_timeout=5)
        pong = client.ping()
        client.close()
        return CheckResult("redis", required=True, ok=bool(pong), detail="PONG" if pong else "no pong")
    except Exception as exc:
        return CheckResult("redis", required=True, ok=False, detail=str(exc))


def check_elasticsearch(settings: Settings) -> CheckResult:
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{settings.elasticsearch_url.rstrip('/')}/_cluster/health")
        if response.status_code != 200:
            return CheckResult("elasticsearch", required=False, ok=False, detail=f"HTTP {response.status_code}")
        health = response.json()
        return CheckResult("elasticsearch", required=False, ok=True, detail=f"status={health.get('status')}")
    except Exception as exc:
        return CheckResult("elasticsearch", required=False, ok=False, detail=str(exc))


def check_minio(settings: Settings) -> CheckResult:
    required = settings.artifact_storage_backend == "minio"
    if not required:
        return CheckResult("minio", required=False, ok=True, detail="skipped: local storage")
    try:
        from app.services.storage.artifacts import MinioArtifactStorage

        MinioArtifactStorage(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket=settings.minio_bucket,
            secure=settings.minio_secure,
        )
        return CheckResult("minio", required=True, ok=True, detail=f"bucket ready: {settings.minio_bucket}")
    except Exception as exc:
        return CheckResult("minio", required=True, ok=False, detail=str(exc))


def run_checks(settings: Settings) -> list[CheckResult]:
    return [
        check_mysql(settings),
        check_redis(settings),
        check_elasticsearch(settings),
        check_minio(settings),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify infrastructure connectivity for the current profile.")
    parser.add_argument("--json", action="store_true", help="Print results as JSON lines.")
    args = parser.parse_args()

    settings = Settings()
    results = run_checks(settings)
    print(f"profile={settings.environment} task_mode={settings.task_mode} storage={settings.artifact_storage_backend}")
    for result in results:
        status = "ok" if result.ok else ("FAIL" if result.required else "warn")
        if args.json:
            import json

            print(json.dumps({"name": result.name, "required": result.required, "ok": result.ok, "detail": result.detail}))
        else:
            print(f"[{status:>4}] {result.name}: {result.detail}")

    return 1 if any(not result.ok and result.required for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
