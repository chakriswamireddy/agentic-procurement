from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorInfo(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorInfo


class HealthComponent(BaseModel):
    status: str
    latency_ms: int | None = None
    required: bool = False


class HealthChecks(BaseModel):
    model_config = ConfigDict(extra="allow")
