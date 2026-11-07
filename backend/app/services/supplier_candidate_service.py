"""Assemble supplier candidates from PostgreSQL identity/quotations and Mongo profiles.

Profiles are fetched in one batched ``$in`` lookup — never one query per candidate —
and missing profiles degrade to an empty profile instead of a failure. Missing fields
are left empty for validation to judge; nothing is fabricated here.
"""

from typing import Any

from pymongo.errors import PyMongoError

from app.core.errors import DependencyUnavailableError
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

        supplier_ids = list(dict.fromkeys(supplier.id for supplier, _ in rows))
        # A Mongo outage is a retryable dependency failure, not an unexpected crash:
        # translate it so the runner can retry and route supplier_unavailable instead
        # of wrapping it as a non-retryable unexpected error.
        try:
            profiles = await self.profiles.get_profiles(supplier_ids)
        except PyMongoError as exc:
            raise DependencyUnavailableError(
                details={"cause": type(exc).__name__}
            ) from exc

        candidates: list[dict[str, Any]] = []
        for supplier, quotation in rows:
            profile = profiles.get(supplier.id)
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
                    "profile": profile.model_dump(mode="json") if profile else None,
                }
            )

        return candidates
