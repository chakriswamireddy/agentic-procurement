from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_serializer


class ProcurementConstraints(BaseModel):
    max_delivery_days: int | None = Field(default=None, ge=0)
    required_certifications: list[str] = Field(default_factory=list)
    max_unit_price: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None

    @field_serializer("max_unit_price")
    def _serialize_max_unit_price(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)


class CreateProcurementRequest(BaseModel):
    product_id: str
    quantity: int = Field(gt=0, le=100000)
    constraints: ProcurementConstraints = Field(default_factory=ProcurementConstraints)


class RecommendationSummary(BaseModel):
    id: str | None = None
    supplier_id: str
    supplier_name: str
    score: str
    scoring_version: str
    total_cost: str
    unit_price: str
    currency: str
    delivery_days: int
    version: int
    caveats: list[str] = Field(default_factory=list)
    evidence_chunk_ids: list[str] = Field(default_factory=list)


class ProcurementRequestResponse(BaseModel):
    id: str
    thread_id: str
    requester_id: str
    product_id: str
    product_name: str | None = None
    category: str | None = None
    quantity: int
    constraints: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: datetime | None = None
    recommendation: RecommendationSummary | None = None
