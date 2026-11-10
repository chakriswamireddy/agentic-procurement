from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]

_SECRET_KEY_PARTS = ("secret", "password", "token", "api_key", "apikey")


def redact_value(key: str, value: Any) -> Any:
    lowered = key.lower()
    if any(part in lowered for part in _SECRET_KEY_PARTS):
        return "***"

    if isinstance(value, str) and "://" in value and "@" in value:
        scheme, remainder = value.split("://", 1)
        credentials, host = remainder.rsplit("@", 1)
        user = credentials.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"

    return value


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str
    mongodb_url: str
    mongodb_db: str = "procurement"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "policy_chunks"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    sparse_embedding_model: str = "Qdrant/bm25"
    embedding_batch_size: int = 32
    embedding_timeout_seconds: float = 120.0
    fastembed_cache_dir: str | None = None
    retrieval_candidate_k: int = 20
    retrieval_result_limit: int = 5
    retrieval_min_dense_score: float = 0.60
    retrieval_min_sparse_score: float = 2.0
    retrieval_min_text_chars: int = 40
    rrf_k: int = 60
    checkpointer_database_url: str = (
        "postgresql://procurement:procurement@localhost:5432/procurement"
    )
    graph_checkpointer_enabled: bool = True
    workflow_recursion_limit: int = 25
    workflow_as_of: date | None = None
    workflow_supplier_timeout_seconds: float = 5.0
    workflow_policy_timeout_seconds: float = 8.0
    workflow_compare_timeout_seconds: float = 1.0
    workflow_validate_timeout_seconds: float = 1.0
    workflow_execute_timeout_seconds: float = 10.0
    workflow_research_deadline_seconds: float = 12.0
    workflow_execute_deadline_seconds: float = 15.0
    workflow_specialist_max_attempts: int = 3
    workflow_specialist_base_delay_seconds: float = 0.2
    workflow_specialist_max_delay_seconds: float = 2.0
    workflow_max_supplier_candidates: int = 200
    workflow_max_policy_evidence: int = 5
    jwt_secret: str
    jwt_issuer: str = "agentic-procurement"
    jwt_audience: str = "agentic-procurement-api"
    jwt_ttl_minutes: int = 30
    log_level: str = "INFO"

    # Auth rate limiting (Phase 6); disabled under APP_ENV=test
    auth_rate_limit_enabled: bool = True
    auth_rate_limit_requests: int = 5
    auth_rate_limit_window_seconds: int = 60

    # MCP server/client (Phase 5)
    mcp_server_command: str = "python"
    mcp_server_args: str = '["-m","app.mcp.server"]'
    mcp_tool_timeout_s: float = 10.0
    mcp_use_client: bool = False

    # Production pool and caching configuration (Phase 6)
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout: float = 10.0
    database_pool_recycle: int = 1800
    database_pool_pre_ping: bool = True
    redis_cache_enabled: bool = True
    redis_cache_ttl_seconds: int = 3600

    # Production LLM provider configuration (Phase 6)
    llm_provider: str = "simulator"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str | None = None
    llm_base_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @field_validator(
        "database_url",
        "mongodb_url",
        "checkpointer_database_url",
        "jwt_secret",
        "embedding_model",
        "sparse_embedding_model",
    )
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator(
        "embedding_dim",
        "embedding_batch_size",
        "retrieval_candidate_k",
        "retrieval_result_limit",
        "retrieval_min_text_chars",
        "rrf_k",
        "workflow_recursion_limit",
        "workflow_specialist_max_attempts",
        "workflow_max_supplier_candidates",
        "workflow_max_policy_evidence",
    )
    @classmethod
    def _must_be_positive_int(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be positive")
        return value

    @field_validator(
        "embedding_timeout_seconds",
        "retrieval_min_dense_score",
        "retrieval_min_sparse_score",
        "workflow_supplier_timeout_seconds",
        "workflow_policy_timeout_seconds",
        "workflow_compare_timeout_seconds",
        "workflow_validate_timeout_seconds",
        "workflow_execute_timeout_seconds",
        "workflow_research_deadline_seconds",
        "workflow_execute_deadline_seconds",
        "workflow_specialist_base_delay_seconds",
        "workflow_specialist_max_delay_seconds",
    )
    @classmethod
    def _must_be_positive_float(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("must be positive")
        return value

    @field_validator("log_level")
    @classmethod
    def _normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_strength(cls, value: str) -> str:
        if len(value.encode("utf-8")) < 32:
            raise ValueError("jwt_secret must be at least 32 bytes long")
        return value

    @field_validator(
        "jwt_ttl_minutes",
        "auth_rate_limit_requests",
        "auth_rate_limit_window_seconds",
    )
    @classmethod
    def _must_be_positive_int_settings(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be positive")
        return value

    def safe_dict(self) -> dict[str, Any]:
        return {key: redact_value(key, value) for key, value in self.model_dump().items()}

    def __repr__(self) -> str:
        values = ", ".join(f"{key}={value!r}" for key, value in self.safe_dict().items())
        return f"{type(self).__name__}({values})"

    __str__ = __repr__


@lru_cache
def get_settings() -> Settings:
    return Settings()
