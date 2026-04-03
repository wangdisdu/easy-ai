from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.app.agent_app import AgentApp
from app.app.app_runtime import AppRuntime
from app.app.llm_app import LlmApp
from app.app.rag_app import RagApp
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext, build_request_context
from app.core.response import Resp
from app.db.session import get_db
from app.model.open_model import (
    AgentRunRequest,
    AppRunReq,
    AppTestReq,
    LlmAppRunReq,
    RagRunRequest,
)

router = APIRouter(prefix="/open/app", tags=["open-app"])
app_runtime = AppRuntime()
llm_app = LlmApp(app_runtime=app_runtime)
agent_app = AgentApp(app_runtime=app_runtime)
rag_app = RagApp(app_runtime=app_runtime)


@router.post("/{app_id}", response_model=Resp[dict[str, Any]])
def run_app(
    app_id: int,
    req: AppRunReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[dict[str, Any]]:
    return Resp(data=_dispatch(db=db, app_id=app_id, req=req, req_ctx=req_ctx, is_test=False))


@router.post("/{app_id}/test", response_model=Resp[dict[str, Any]])
def test_app(
    app_id: int,
    req: AppTestReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[dict[str, Any]]:
    return Resp(data=_dispatch(db=db, app_id=app_id, req=req, req_ctx=req_ctx, is_test=True))


def _dispatch(
    *,
    db: Session,
    app_id: int,
    req: AppRunReq,
    req_ctx: RequestContext,
    is_test: bool,
) -> dict[str, Any]:
    app = app_runtime.get_app(db, app_id)
    # request_type 枚举：test-平台测试；chat-平台对话；api-API 调用
    request_type = "test" if is_test else "api"

    if app.app_type == "llm":
        llm_req = LlmAppRunReq(app_id=app_id, inputs=req.inputs, messages=req.messages)
        return llm_app.run(db=db, req=llm_req, req_ctx=req_ctx, request_type=request_type)

    if app.app_type == "agent":
        agent_req = AgentRunRequest(app_id=app_id, messages=req.messages, variables=req.variables)
        return agent_app.run(db=db, req=agent_req, req_ctx=req_ctx, request_type=request_type)

    if app.app_type == "rag":
        query = _resolve_query(req)
        rag_req = RagRunRequest(app_id=app_id, query=query, variables=req.variables)
        return rag_app.run(
            db=db,
            req=rag_req,
            req_ctx=req_ctx,
            request_type=request_type,
        ).model_dump()

    raise ServiceError(ErrorCode.BAD_REQUEST, f"app type not supported yet: {app.app_type}")


def _resolve_query(req: AppRunReq) -> str:
    if req.query and req.query.strip():
        return req.query.strip()

    query = req.inputs.get("query")
    if isinstance(query, str) and query.strip():
        return query.strip()

    for message in reversed(req.messages):
        if message.role == "user" and message.content.strip():
            return message.content.strip()

    raise ServiceError(ErrorCode.BAD_REQUEST, "query is required for rag app")
