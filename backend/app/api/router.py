from fastapi import APIRouter, Depends

from app.api.alert_record_api import router as alert_record_router
from app.api.alert_rule_api import router as alert_rule_router
from app.api.app_api import router as app_router
from app.api.app_category_api import router as app_category_router
from app.api.auth_api import router as auth_router
from app.api.conversation_api import router as conversation_router
from app.api.integration_api import router as integration_router
from app.api.kb_api import router as kb_router
from app.api.kb_category_api import router as kb_category_router
from app.api.kb_document_api import router as kb_document_router
from app.api.llm_api import router as llm_router
from app.api.memory_api import router as memory_router
from app.api.observability_api import router as observability_router
from app.api.open_api import router as open_router
from app.api.permission_api import router as permission_router
from app.api.policy_api import policy_router
from app.api.policy_api import router as tool_policy_router
from app.api.rag_dataset_api import router as rag_dataset_router
from app.api.role_api import router as role_router
from app.api.sandbox_image_api import router as sandbox_image_router
from app.api.sandbox_instance_api import router as sandbox_instance_router
from app.api.sandbox_view_api import router as sandbox_view_router
from app.api.skill_api import router as skill_router
from app.api.sync_log_api import router as sync_log_router
from app.api.system_setting_api import router as system_setting_router
from app.api.tool_api import mcp_router
from app.api.tool_api import router as tool_router
from app.api.user_api import router as user_router
from app.api.user_group_api import router as user_group_router
from app.core.request_context import require_authenticated_user

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
_login_required = [Depends(require_authenticated_user)]
api_router.include_router(user_router, dependencies=_login_required)
api_router.include_router(user_group_router, dependencies=_login_required)
api_router.include_router(role_router, dependencies=_login_required)
api_router.include_router(permission_router, dependencies=_login_required)
api_router.include_router(app_category_router, dependencies=_login_required)
api_router.include_router(app_router, dependencies=_login_required)
api_router.include_router(open_router, dependencies=_login_required)
api_router.include_router(skill_router, dependencies=_login_required)
api_router.include_router(tool_router, dependencies=_login_required)
api_router.include_router(tool_policy_router, dependencies=_login_required)
api_router.include_router(policy_router, dependencies=_login_required)
api_router.include_router(mcp_router, dependencies=_login_required)
api_router.include_router(llm_router, dependencies=_login_required)
api_router.include_router(observability_router, dependencies=_login_required)
api_router.include_router(alert_rule_router, dependencies=_login_required)
api_router.include_router(alert_record_router, dependencies=_login_required)
api_router.include_router(conversation_router, dependencies=_login_required)
api_router.include_router(memory_router, dependencies=_login_required)
api_router.include_router(system_setting_router, dependencies=_login_required)
api_router.include_router(integration_router, dependencies=_login_required)
api_router.include_router(sandbox_image_router, dependencies=_login_required)
api_router.include_router(sandbox_instance_router, dependencies=_login_required)
api_router.include_router(sandbox_view_router, dependencies=_login_required)
api_router.include_router(kb_document_router, dependencies=_login_required)
api_router.include_router(kb_category_router, dependencies=_login_required)
api_router.include_router(kb_router, dependencies=_login_required)
api_router.include_router(rag_dataset_router, dependencies=_login_required)
api_router.include_router(sync_log_router, dependencies=_login_required)
