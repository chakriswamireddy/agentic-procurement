from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

SupplierStatus = Literal["active", "inactive", "suspended"]


class SupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    category: str
    location: str
    status: SupplierStatus


class SupplierProfile(BaseModel):
    supplier_type: str | None = None
    certifications: list[str] = Field(default_factory=list)
    compliance: dict[str, Any] = Field(default_factory=dict)
    regional_registrations: dict[str, Any] = Field(default_factory=dict)
    source: dict[str, Any] = Field(default_factory=dict)


class QuotationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: str
    unit_price: Decimal
    currency: str
    available_quantity: int
    delivery_days: int
    valid_until: date

    @field_serializer("unit_price")
    def _serialize_unit_price(self, value: Decimal) -> str:
        return str(value)


class SupplierDetail(SupplierRead):
    profile: SupplierProfile | None = None
    quotations: list[QuotationSummary] = Field(default_factory=list)
    profile_store_available: bool = Field(default=True, exclude=True)


class SupplierList(BaseModel):
    items: list[SupplierRead]
    total: int
    limit: int
    offset: int
