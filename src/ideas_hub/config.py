from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["local", "openrouter", "openai", "anthropic"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://ideas:ideas@localhost:5432/ideas"
    redis_url: str = "redis://localhost:6379/0"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "ideas-hub"
    minio_secure: bool = False

    local_llm_base_url: str = "http://localhost:8001/v1"
    local_llm_api_key: str = "local"
    local_llm_model: str = "local-model"

    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-sonnet-4"
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    task_article_extract_provider: ProviderName = "local"
    task_event_summary_provider: ProviderName = "local"
    task_opportunity_generate_provider: ProviderName = "local"
    task_opportunity_skeptic_provider: ProviderName = "local"
    task_opportunity_judge_provider: ProviderName = "local"

    embedding_model: str = "BAAI/bge-m3"
    event_similarity_threshold: float = 0.82
    cloud_fallback_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
