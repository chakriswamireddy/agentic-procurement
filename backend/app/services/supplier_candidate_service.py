"""Assemble supplier candidates from PostgreSQL identity/quotations and Mongo profiles."""

from typing import Any

from app.repositories.supplier_profile_repository import SupplierProfileRepository
from app.repositories.supplier_repository import SupplierRepository


class SupplierCandidateService:
    def __init__(
        self,
        suppliers: SupplierRepository,
        profiles: SupplierProfileRepository,
    ) -> None:
        self.suppliers = suppliers
        self.profiles = profiles

    async def candidates(
        self, *, request: dict[str, Any], as_of: str
    ) -> list[dict[str, Any]]:
        del as_of  # eligibility is evaluated by the comparison service
        product_id = str(request.get("product_id", ""))
        rows = await self.suppliers.list_quotation_candidates(product_id)

        profiles: dict[str, dict[str, Any] | None] = {}
        candidates: list[dict[str, Any]] = []
        for supplier, quotation in rows:
            if supplier.id not in profiles:
                profile = await self.profiles.get_profile(supplier.id)
                profiles[supplier.id] = (
                    profile.model_dump(mode="json") if profile is not None else None
                )
            candidates.append(
                {
                    "supplier_id": supplier.id,
                    "supplier_name": supplier.name,
                    "supplier_category": supplier.category,
                    "supplier_status": supplier.status,
                    "quotation_id": quotation.id,
                    "product_id": quotation.product_id,
                    "unit_price": str(quotation.unit_price),
                    "currency": quotation.currency,
                    "available_quantity": quotation.available_quantity,
                    "delivery_days": quotation.delivery_days,
                    "valid_until": quotation.valid_until.isoformat(),
                    "profile": profiles[supplier.id],
                }
            )

        return candidates
