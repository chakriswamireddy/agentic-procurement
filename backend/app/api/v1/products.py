from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.deps import CurrentUserDep, WorkflowServiceDep
from app.schemas.procurement import ProductRead

router = APIRouter(prefix="/products", tags=["products"])


@router.get(
    "",
    response_model=list[ProductRead],
    operation_id="list_products",
)
async def list_products(
    service: WorkflowServiceDep,
    response: Response,
    current_user: CurrentUserDep,
    category: Annotated[str | None, Query(max_length=100)] = None,
) -> list[ProductRead]:
    del current_user
    response.headers["Cache-Control"] = "no-store"
    items = await service.list_products(category=category)
    return [ProductRead.model_validate(item) for item in items]
