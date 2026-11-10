from typing import Annotated

from fastapi import APIRouter, Path, Query, Response

from app.api.deps import CurrentUserDep, SupplierServiceDep
from app.schemas.supplier import SupplierDetail, SupplierList, SupplierStatus

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get(
    "",
    response_model=SupplierList,
    operation_id="list_suppliers",
)
async def list_suppliers(
    service: SupplierServiceDep,
    response: Response,
    current_user: CurrentUserDep,
    category: Annotated[str | None, Query(max_length=100)] = None,
    location: Annotated[str | None, Query(max_length=32)] = None,
    status: Annotated[SupplierStatus | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SupplierList:
    del current_user
    response.headers["Cache-Control"] = "no-store"
    return await service.list_suppliers(
        category=category,
        location=location,
        status=status,
        q=q,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{supplier_id}",
    response_model=SupplierDetail,
    operation_id="get_supplier",
)
async def get_supplier(
    service: SupplierServiceDep,
    response: Response,
    supplier_id: Annotated[str, Path(min_length=1, max_length=64)],
    current_user: CurrentUserDep,
) -> SupplierDetail:
    del current_user
    response.headers["Cache-Control"] = "no-store"
    supplier = await service.get_supplier(supplier_id)
    if not supplier.profile_store_available:
        response.headers["X-Profile-Status"] = "unavailable"
    return supplier
