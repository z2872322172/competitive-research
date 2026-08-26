import os
from functools import lru_cache
from typing import Any
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROFILE_DEFAULTS: dict[str, dict[str, Any]] = {
    "dev": {
        "database_url": "sqlite:///./verda_dev.db",
        "redis_url": "redis://localhost:6379/0",
        "celery_broker_url": "redis://localhost:6379/0",
        "celery_result_backend": "redis://localhost:6379/1",
        "task_mode": "inline",
        "artifact_storage_dir": "storage",
        "mysql_host": "localhost",
        "mysql_port": 3306,
        "mysql_user": "verda",
        "mysql_password": "verda",
        "mysql_database": "verda",
        "redis_host": "localhost",
        "redis_port": 6379,
        "redis_db": 0,
        "celery_result_db": 1,
        "elasticsearch_url": "http://localhost:9200",
        "minio_endpoint": "http://localhost:9000",
        "artifact_storage_backend": "local",
    },
    "test": {
        "database_url": "sqlite:///./verda_test.db",
        "redis_url": "redis://localhost:6379/2",
        "celery_broker_url": "redis://localhost:6379/2",
        "celery_result_backend": "redis://localhost:6379/3",
        "task_mode": "inline",
        "artifact_storage_dir": "storage/test",
        "mysql_host": "localhost",
        "mysql_port": 3306,
        "mysql_user": "verda",
        "mysql_password": "verda",
        "mysql_database": "verda_test",
        "redis_host": "localhost",
        "redis_port": 6379,
        "redis_db": 2,
        "celery_result_db": 3,
        "elasticsearch_url": "http://localhost:9200",
        "minio_endpoint": "http://localhost:9000",
        "artifact_storage_backend": "local",
    },
    "prod": {
        "database_url": "mysql+pymysql://verda:verda@mysql:3306/verda",
        "redis_url": "redis://redis:6379/0",
        "celery_broker_url": "redis://redis:6379/0",
        "celery_result_backend": "redis://redis:6379/1",
        "task_mode": "celery",
        "artifact_storage_dir": "storage/prod",
        "mysql_host": "mysql",
        "mysql_port": 3306,
        "mysql_user": "verda",
        "mysql_password": "verda",
        "mysql_database": "verda",
        "redis_host": "redis",
        "redis_port": 6379,
        "redis_db": 0,
        "celery_result_db": 1,
        "elasticsearch_url": "http://elasticsearch:9200",
        "minio_endpoint": "http://minio:9000",
        "artifact_storage_backend": "minio",
    },
}

ENVIRONMENT_ALIASES = {
    "development": "dev",
    "local": "dev",
    "testing": "test",
    "production": "prod",
}

ENV_FIELD_NAMES = {
    "database_url": "DATABASE_URL",
    "redis_url": "REDIS_URL",
    "celery_broker_url": "CELERY_BROKER_URL",
    "celery_result_backend": "CELERY_RESULT_BACKEND",
    "task_mode": "TASK_MODE",
    "artifact_storage_dir": "ARTIFACT_STORAGE_DIR",
    "mysql_host": "MYSQL_HOST",
    "mysql_port": "MYSQL_PORT",
    "mysql_user": "MYSQL_USER",
    "mysql_password": "MYSQL_PASSWORD",
    "mysql_database": "MYSQL_DATABASE",
    "redis_host": "REDIS_HOST",
    "redis_port": "REDIS_PORT",
    "redis_db": "REDIS_DB",
    "celery_result_db": "CELERY_RESULT_DB",
    "elasticsearch_url": "ELASTICSEARCH_URL",
    "minio_endpoint": "MINIO_ENDPOINT",
    "artifact_storage_backend": "ARTIFACT_STORAGE_BACKEND",
}


def default_environment() -> str:
    return os.getenv("APP_ENV") or os.getenv("ENVIRONMENT") or "dev"


def normalize_environment(value: str) -> str:
    normalized = value.strip().lower()
    return ENVIRONMENT_ALIASES.get(normalized, normalized)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Verda Competitive Research API"
    environment: str = Field(default_factory=default_environment)
    api_prefix: str = "/v1"

    database_url: str = Field(default="sqlite:///./verda_dev.db")
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "verda"
    mysql_password: str = "verda"
    mysql_database: str = "verda"

    redis_url: str = Field(default="redis://localhost:6379/0")
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = Field(default=0, ge=0)
    celery_result_db: int = Field(default=1, ge=0)
    celery_broker_url: str = Field(default="redis://localhost:6379/0")
    celery_result_backend: str = Field(default="redis://localhost:6379/1")
    task_mode: str = Field(default="inline", description="inline or celery")

    elasticsearch_url: str = "http://localhost:9200"
    minio_endpoint: str = "http://localhost:9000"
    minio_access_key: str = "minio"
    minio_secret_key: str = "minio123"
    minio_bucket: str = "verda-artifacts"
    minio_secure: bool = False
    artifact_storage_backend: str = "local"

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    search_provider: str = Field(default="tavily")
    tavily_api_key: str | None = None
    search_max_results: int = Field(default=5, ge=1, le=20)
    fetch_timeout_seconds: float = Field(default=12.0, gt=0)
    fetch_max_retries: int = Field(default=2, ge=0, le=5)
    fetch_retry_backoff_seconds: float = Field(default=0.5, ge=0)
    fetch_rate_limit_seconds: float = Field(default=1.0, ge=0)
    fetch_max_bytes: int = Field(default=1_500_000, ge=100_000)
    fetch_respect_robots: bool = True
    fetch_user_agent: str = "VerdaCompetitiveResearchBot/0.1 (+local development)"
    parser_prefer_trafilatura: bool = True
    min_source_text_chars: int = Field(default=400, ge=80)
    artifact_storage_dir: str = "storage"

    llm_provider: str = Field(default="openai")
    llm_api_key: str | None = None
    openai_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "chat-latest"
    llm_timeout_seconds: float = Field(default=30.0, gt=0)
    llm_max_evidence_items: int = Field(default=8, ge=1, le=30)

    def model_post_init(self, __context: Any) -> None:
        explicit_profile = os.getenv("APP_ENV") or os.getenv("ENVIRONMENT")
        profile = normalize_environment(explicit_profile or self.environment)
        self.environment = profile
        defaults = PROFILE_DEFAULTS.get(profile)
        if defaults is None:
            return

        for field_name, profile_value in defaults.items():
            env_name = ENV_FIELD_NAMES[field_name]
            base_default = type(self).model_fields[field_name].default
            if os.getenv(env_name) is None and (explicit_profile is not None or getattr(self, field_name) == base_default):
                setattr(self, field_name, profile_value)

        self.apply_composed_middleware_urls()

    def apply_composed_middleware_urls(self) -> None:
        mysql_fields = {"MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE"}
        if os.getenv("DATABASE_URL") is None and mysql_fields.intersection(os.environ):
            user = quote_plus(self.mysql_user)
            password = quote_plus(self.mysql_password)
            self.database_url = f"mysql+pymysql://{user}:{password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"

        redis_fields = {"REDIS_HOST", "REDIS_PORT", "REDIS_DB", "CELERY_RESULT_DB"}
        if redis_fields.intersection(os.environ):
            redis_url = f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
            result_backend = f"redis://{self.redis_host}:{self.redis_port}/{self.celery_result_db}"
            if os.getenv("REDIS_URL") is None:
                self.redis_url = redis_url
            if os.getenv("CELERY_BROKER_URL") is None:
                self.celery_broker_url = redis_url
            if os.getenv("CELERY_RESULT_BACKEND") is None:
                self.celery_result_backend = result_backend


@lru_cache
def get_settings() -> Settings:
    return Settings()
