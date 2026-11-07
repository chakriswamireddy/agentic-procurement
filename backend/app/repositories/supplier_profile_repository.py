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

    async def get_profiles(self, supplier_ids: list[str]) -> dict[str, SupplierProfile]:
        """Batch lookup with ``$in`` so candidate assembly never issues N+1 queries."""
        if not supplier_ids:
            return {}
        profiles: dict[str, SupplierProfile] = {}
        async for document in self.database["supplier_profiles"].find(
            {"_id": {"$in": supplier_ids}}
        ):
            supplier_id = str(document.get("_id", ""))
            profiles[supplier_id] = SupplierProfile.model_validate(document)
        return profiles
