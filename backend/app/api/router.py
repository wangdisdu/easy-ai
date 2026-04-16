from fastapi import APIRouter

from app.api.app_api import router as app_router
from app.api.auth_api import router as auth_router
from app.api.conversation_api import router as conversation_router
from app.api.llm_api import router as llm_router
from app.api.observability_api import router as observability_router
from app.api.open_api import router as open_router
from app.api.role_api import router as role_router
from app.api.skill_api import router as skill_router
from app.api.tool_api import mcp_router
from app.api.tool_api import router as tool_router
from app.api.user_api import router as user_router
from app.api.user_group_api import router as user_group_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(user_router)
api_router.include_router(auth_router)
api_router.include_router(user_group_router)
api_router.include_router(role_router)
api_router.include_router(app_router)
api_router.include_router(open_router)
api_router.include_router(skill_router)
api_router.include_router(tool_router)
api_router.include_router(mcp_router)
api_router.include_router(llm_router)
api_router.include_router(observability_router)
api_router.include_router(conversation_router)
