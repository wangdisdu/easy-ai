from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.policy_model import PolicyOptionsResp, PolicyResp, PolicyUpdateReq
from app.service.policy_service import PolicyService, get_policy_options

router = APIRouter(prefix="/tool", tags=["tool-policy"])
policy_router = APIRouter(prefix="/policy", tags=["tool-policy"])

service = PolicyService(SnowflakeGenerator(settings.snowflake_worker_id))


@router.get("/{tool_id}/policy", response_model=Resp[PolicyResp])
def get_tool_policy(tool_id: str, db: Session = Depends(get_db)) -> Resp[PolicyResp]:
    return Resp(data=service.get_policy_for_tool(db, int(tool_id)))


@router.put("/{tool_id}/policy", response_model=Resp[PolicyResp])
def replace_tool_policy(
    tool_id: str,
    req: PolicyUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[PolicyResp]:
    return Resp(data=service.replace_policy(db, int(tool_id), req, req_ctx))


@policy_router.get("/options", response_model=Resp[PolicyOptionsResp])
def list_policy_options() -> Resp[PolicyOptionsResp]:
    """返回前端 form 渲染需要的 actions / operators / context_variables 元数据。"""
    return Resp(data=get_policy_options())
