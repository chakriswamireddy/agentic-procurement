from pymongo.asynchronous.database import AsyncDatabase

from app.schemas.supplier import SupplierProfile


class SupplierProfileRepository:
    def __init__(self, database: AsyncDatabase) -> None:
        self.database = database

    async def get_profile(self, supplier_id: str) -> SupplierProfile | None:
        document = await self.database["supplier_profiles"].find_one({"_id": supplier_id})
        if document is None:
            return None
        return SupplierProfile.model_validate(document)
