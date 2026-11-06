from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.postgres.models import Quotation, Supplier


class SupplierRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    def _filters(
        self,
        *,
        category: str | None,
        location: str | None,
        status: str | None,
        q: str | None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if category is not None:
            filters.append(Supplier.category == category)
        if location is not None:
            filters.append(Supplier.location == location)
        if status is not None:
            filters.append(Supplier.status == status)
        if q is not None:
            pattern = f"%{self._escape_like(q)}%"
            filters.append(Supplier.name.ilike(pattern, escape="\\"))
        return filters

    async def list_suppliers(
        self,
        *,
        category: str | None,
        location: str | None,
        status: str | None,
        q: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Supplier], int]:
        filters = self._filters(
            category=category,
            location=location,
            status=status,
            q=q,
        )

        count_statement = select(func.count()).select_from(Supplier).where(*filters)
        page_statement = (
            select(Supplier)
            .where(*filters)
            .order_by(Supplier.name, Supplier.id)
            .limit(limit)
            .offset(offset)
        )

        total = (await self.session.execute(count_statement)).scalar_one()
        rows = list((await self.session.execute(page_statement)).scalars().all())
        return rows, total

    async def get_supplier(self, supplier_id: str) -> Supplier | None:
        statement = (
            select(Supplier)
            .options(selectinload(Supplier.quotations))
            .where(Supplier.id == supplier_id)
        )
        return (await self.session.execute(statement)).scalar_one_or_none()

    async def list_quotation_candidates(
        self, product_id: str
    ) -> list[tuple[Supplier, Quotation]]:
        """Return every supplier quotation for a product, including ineligible ones.

        The comparison service records exclusion reasons, so this query must not
        pre-filter by supplier status, expiry, or constraints.
        """
        statement = (
            select(Supplier, Quotation)
            .join(Quotation, Quotation.supplier_id == Supplier.id)
            .where(Quotation.product_id == product_id)
            .order_by(Supplier.id, Quotation.id)
        )
        rows = (await self.session.execute(statement)).all()
        return [(supplier, quotation) for supplier, quotation in rows]
