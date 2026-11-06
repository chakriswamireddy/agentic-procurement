from typing import Annotated

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.mongodb.client import get_database
from app.database.postgres.session import get_db_session
from app.repositories.supplier_profile_repository import SupplierProfileRepository
from app.repositories.supplier_repository import SupplierRepository
from app.services.supplier_service import SupplierService


def get_mongo_db() -> AsyncDatabase:
    return get_database()


def get_supplier_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    mongo_db: Annotated[AsyncDatabase, Depends(get_mongo_db)],
) -> SupplierService:
    return SupplierService(
        suppliers=SupplierRepository(session),
        profiles=SupplierProfileRepository(mongo_db),
    )


SupplierServiceDep = Annotated[SupplierService, Depends(get_supplier_service)]
