import logging

from pymongo.errors import PyMongoError
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import DependencyUnavailableError, NotFoundError, ValidationError
from app.database.postgres.engine import is_database_unavailable
from app.repositories.supplier_profile_repository import SupplierProfileRepository
from app.repositories.supplier_repository import SupplierRepository
from app.schemas.supplier import SupplierDetail, SupplierList, SupplierRead

logger = logging.getLogger(__name__)

VALID_SUPPLIER_STATUSES = frozenset({"active", "inactive", "suspended"})


class SupplierService:
    def __init__(
        self,
        suppliers: SupplierRepository,
        profiles: SupplierProfileRepository,
    ) -> None:
        self.suppliers = suppliers
        self.profiles = profiles

    @staticmethod
    def _normalize(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    @staticmethod
    def _normalize_search(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @classmethod
    def _normalize_status(cls, status: str | None) -> str | None:
        normalized = cls._normalize(status)
        if normalized is not None and normalized not in VALID_SUPPLIER_STATUSES:
            raise ValidationError(
                "invalid supplier status",
                details={"allowed": sorted(VALID_SUPPLIER_STATUSES)},
            )
        return normalized

    async def list_suppliers(
        self,
        *,
        category: str | None = None,
        location: str | None = None,
        status: str | None = None,
        q: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SupplierList:
        try:
            rows, total = await self.suppliers.list_suppliers(
                category=self._normalize(category),
                location=self._normalize(location),
                status=self._normalize_status(status),
                q=self._normalize_search(q),
                limit=limit,
                offset=offset,
            )
        except (SQLAlchemyError, OSError) as exc:
            if is_database_unavailable(exc):
                raise DependencyUnavailableError("database unavailable") from exc
            raise

        return SupplierList(
            items=[SupplierRead.model_validate(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_supplier(self, supplier_id: str) -> SupplierDetail:
        try:
            supplier = await self.suppliers.get_supplier(supplier_id)
        except (SQLAlchemyError, OSError) as exc:
            if is_database_unavailable(exc):
                raise DependencyUnavailableError("database unavailable") from exc
            raise

        if supplier is None:
            raise NotFoundError(f"supplier {supplier_id} not found")

        detail = SupplierDetail.model_validate(supplier)
        try:
            detail.profile = await self.profiles.get_profile(supplier_id)
        except (PyMongoError, OSError):
            logger.warning(
                "supplier profile store unavailable",
                extra={"path": f"/suppliers/{supplier_id}"},
            )
            detail.profile = None
            detail.profile_store_available = False

        return detail
