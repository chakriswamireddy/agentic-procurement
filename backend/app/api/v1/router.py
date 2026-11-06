from fastapi import APIRouter

from app.api.v1.suppliers import router as suppliers_router

router = APIRouter(prefix="/api/v1")
router.include_router(suppliers_router)
