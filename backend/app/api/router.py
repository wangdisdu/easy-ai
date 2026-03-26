from fastapi import APIRouter

from app.api.auth_api import router as auth_router
from app.api.role_api import router as role_router
from app.api.user_api import router as user_router
from app.api.user_group_api import router as user_group_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(user_router)
api_router.include_router(auth_router)
api_router.include_router(user_group_router)
api_router.include_router(role_router)
