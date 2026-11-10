"""Typed input/output schemas for procurement MCP tools (Phase 5.9)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


class ToolError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class SearchSuppliersInput(BaseModel):
    category: str = Field(min_length=1, max_length=64)
    quantity: int = Field(gt=0, le=100000)
    max_delivery_days: int | None = Field(default=None, ge=1, le=365)


class SupplierCandidateOut(BaseModel):
    supplier_id: str
    name: str
    category: str
    location: str
    status: str
    unit_price: str | None = None
    currency: str | None = None
    delivery_days: int | None = None


class SearchSuppliersOutput(BaseModel):
    schema_version: str = SCHEMA_VERSION
    candidates: list[SupplierCandidateOut]
    count: int


class GetSupplierQuotationInput(BaseModel):
    supplier_id: str = Field(min_length=1, max_length=64)
    product_id: str = Field(min_length=1, max_length=64)


class QuotationOut(BaseModel):
    quotation_id: str
    supplier_id: str
    product_id: str
    unit_price: str
    currency: str
    available_quantity: int
    delivery_days: int
    valid_until: str | None = None


class GetSupplierQuotationOutput(BaseModel):
    schema_version: str = SCHEMA_VERSION
    quotation: QuotationOut


class GetPolicyEvidenceInput(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    as_of: str | None = Field(default=None, max_length=32)
    classification: str | None = Field(default=None, max_length=64)


class PolicyEvidenceOut(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    text: str
    score: float


class GetPolicyEvidenceOutput(BaseModel):
    schema_version: str = SCHEMA_VERSION
    evidence: list[PolicyEvidenceOut]
    inconclusive: bool = False


class CreatePurchaseRequestInput(BaseModel):
    """Deliberately carries no business values — only identity and idempotency."""

    request_id: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)


class CreatePurchaseRequestOutput(BaseModel):
    schema_version: str = SCHEMA_VERSION
    external_reference: str
    status: Literal["created", "exists"]
    request_id: str
    idempotency_key: str


class GetPurchaseRequestStatusInput(BaseModel):
    external_reference: str = Field(min_length=1, max_length=128)


class GetPurchaseRequestStatusOutput(BaseModel):
    schema_version: str = SCHEMA_VERSION
    external_reference: str
    status: str
    updated_at: str | None = None


def error_payload(code: str, message: str, *, retryable: bool = False) -> dict[str, Any]:
    return ToolError(code=code, message=message, retryable=retryable).model_dump()
