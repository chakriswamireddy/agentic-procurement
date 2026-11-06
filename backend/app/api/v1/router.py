from fastapi import APIRouter

from app.api.v1.documents import router as documents_router
from app.api.v1.policies import router as policies_router
from app.api.v1.suppliers import router as suppliers_router

router = APIRouter(prefix="/api/v1")
router.include_router(suppliers_router)
router.include_router(documents_router)
router.include_router(policies_router)
