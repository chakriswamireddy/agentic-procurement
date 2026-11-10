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

    async def list_products(self, category: str | None = None) -> list[dict[str, Any]]:
        statement = select(Product)
        if category:
            statement = statement.where(Product.category == category)
        statement = statement.order_by(Product.name)
        rows = (await self.session.execute(statement)).scalars().all()
        return [
            {
                "id": p.id,
                "sku": p.sku,
                "name": p.name,
                "category": p.category,
                "attributes": p.attributes_json or {},
            }
            for p in rows
        ]

    async def list_requests(
        self,
        *,
        status: str | None = None,
        requester_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        statement = (
            select(ProcurementRequest, Product)
            .join(Product, Product.id == ProcurementRequest.product_id)
        )
        if status:
            statement = statement.where(ProcurementRequest.status == status)
        if requester_id:
            statement = statement.where(ProcurementRequest.requester_id == requester_id)
        statement = (
            statement.order_by(ProcurementRequest.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(statement)).all()
        return [
            {
                "id": req.id,
                "thread_id": req.id,
                "requester_id": req.requester_id,
                "product_id": req.product_id,
                "product_name": prod.name,
                "category": prod.category,
                "quantity": req.quantity,
                "constraints": req.constraints_json or {},
                "status": req.status,
                "created_at": req.created_at.isoformat(),
            }
            for req, prod in rows
        ]

    async def lock_for_resume(self, request_id: str) -> ProcurementRequest | None:
        statement = (
            select(ProcurementRequest)
            .where(ProcurementRequest.id == request_id)
            .with_for_update()
        )
        return (await self.session.execute(statement)).scalar_one_or_none()
