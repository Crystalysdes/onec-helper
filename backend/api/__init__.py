from fastapi import APIRouter
from .auth import router as auth_router
from .products import router as products_router
from .stores import router as stores_router
from .reports import router as reports_router
from .admin import router as admin_router
from .subscriptions import router as subscriptions_router
from .agent import router as agent_router
from .exports import router as exports_router

api_router = APIRouter()

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(products_router, prefix="/products", tags=["products"])
api_router.include_router(stores_router, prefix="/stores", tags=["stores"])
api_router.include_router(reports_router, prefix="/reports", tags=["reports"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(subscriptions_router, prefix="/subscriptions", tags=["subscriptions"])
api_router.include_router(agent_router, prefix="/agent", tags=["agent"])
api_router.include_router(exports_router, prefix="/exports", tags=["exports"])
