from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.postgres.models import ProcurementRequest, Product


class RequestRepository:
    """PostgreSQL access for procurement requests. Callers commit."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_product(self, product_id: str) -> Product | None:
        return await self.session.get(Product, product_id)

    async def get_request(self, request_id: str) -> ProcurementRequest | None:
        return await self.session.get(ProcurementRequest, request_id)

    async def get_request_view(self, request_id: str) -> dict[str, Any] | None:
        statement = (
            select(ProcurementRequest, Product)
            .join(Product, Product.id == ProcurementRequest.product_id)
            .where(ProcurementRequest.id == request_id)
        )
        row = (await self.session.execute(statement)).first()
        if row is None:
            return None
        request, product = row
        return {
            "id": request.id,
            "requester_id": request.requester_id,
            "product_id": request.product_id,
            "product_name": product.name,
            "category": product.category,
            "quantity": request.quantity,
            "constraints": request.constraints_json or {},
            "status": request.status,
            "created_at": request.created_at.isoformat(),
        }

    async def create(
        self,
        *,
        request_id: str,
        requester_id: str,
        product_id: str,
        quantity: int,
        constraints: dict[str, Any],
        status: str,
    ) -> ProcurementRequest:
        record = ProcurementRequest(
            id=request_id,
            requester_id=requester_id,
            product_id=product_id,
            quantity=quantity,
            constraints_json=constraints,
            status=status,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def set_status(self, request_id: str, status: str) -> bool:
        record = await self.session.get(ProcurementRequest, request_id)
        if record is None:
            return False
        if record.status == status:
            return False
        record.status = status
        await self.session.flush()
        return True
