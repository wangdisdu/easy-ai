import uuid
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.app.agent_app import AgentApp
from app.app.app_runtime import AppRuntime
from app.app.llm_app import LlmApp
from app.app.rag_app import RagApp
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext, build_request_context
from app.core.response import Resp
from app.core.sse import sse_response
from app.db.session import SessionLocal, get_db
from app.model.open_model import (
    AgentRunRequest,
    AppRunReq,
    AppTestHitlRespondReq,
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
async def run_app(
    app_id: int,
    req: AppRunReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[dict[str, Any]]:
    data = await _dispatch(db=db, app_id=app_id, req=req, req_ctx=req_ctx, is_test=False)
    return Resp(data=data)


@router.post("/{app_id}/test", response_model=Resp[dict[str, Any]])
async def test_app(
    app_id: int,
    req: AppTestReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[dict[str, Any]]:
    data = await _dispatch(db=db, app_id=app_id, req=req, req_ctx=req_ctx, is_test=True)
    return Resp(data=data)


@router.post("/{app_id}/stream")
async def run_app_stream(
    app_id: int,
    req: AppRunReq,
    req_ctx: RequestContext = Depends(build_request_context),
) -> StreamingResponse:
    db = SessionLocal()
    try:
        generator = _dispatch_stream(db=db, app_id=app_id, req=req, req_ctx=req_ctx, is_test=False)
    except Exception:
        db.close()
        raise
    return sse_response(generator)


@router.post("/{app_id}/test/stream")
async def test_app_stream(
    app_id: int,
    req: AppTestReq,
    req_ctx: RequestContext = Depends(build_request_context),
) -> StreamingResponse:
    db = SessionLocal()
    try:
        generator = _dispatch_stream(db=db, app_id=app_id, req=req, req_ctx=req_ctx, is_test=True)
    except Exception:
        db.close()
        raise
    return sse_response(generator)


@router.post("/{app_id}/test/hitl/{hitl_id}/respond")
async def test_app_hitl_respond(
    app_id: int,
    hitl_id: str,
    req: AppTestHitlRespondReq,
    req_ctx: RequestContext = Depends(build_request_context),
) -> StreamingResponse:
    """测试流专用 HITL 响应端点，不依赖 TbConversation 记录。

    body: {"thread_id": "...", "action": "confirm"|"modify"|"reject", "parameters": {...}?}
    返回 SSE 流，与 send_message_stream 形态一致。
    """
    db = SessionLocal()
    try:
        agent_req = AgentRunRequest(
            app_id=app_id,
            thread_id=req.thread_id,
            use_checkpoint=True,
        )
        hitl_response: dict[str, Any] = {"action": req.action}
        if req.parameters is not None:
            hitl_response["parameters"] = req.parameters
        generator = agent_app.resume_stream(
            db=db,
            req=agent_req,
            req_ctx=req_ctx,
            hitl_response=hitl_response,
            request_type="test",
        )
    except Exception:
        db.close()
        raise
    return sse_response(generator)


def _dispatch_stream(
    *,
    db: Session,
    app_id: int,
    req: AppRunReq,
    req_ctx: RequestContext,
    is_test: bool,
) -> AsyncGenerator[str, None]:
    """按应用类型分发到对应的流式执行方法。

    db session 的生命周期由各 stream() 方法内部管理（流前关闭，日志写入用独立 session）。
    """
    app = app_runtime.get_app(db, app_id)
    request_type = "test" if is_test else "api"

    if app.app_type == "llm":
        llm_req = LlmAppRunReq(app_id=app_id, inputs=req.inputs, messages=req.messages)
        return llm_app.stream(db=db, req=llm_req, req_ctx=req_ctx, request_type=request_type)

    if app.app_type == "agent":
        # 测试流需要 checkpoint 以支持 HITL（interrupt 需要持久化恢复点）
        thread_id = str(uuid.uuid4()) if is_test else None
        agent_req = AgentRunRequest(
            app_id=app_id,
            messages=req.messages,
            variables=req.variables,
            thread_id=thread_id,
            use_checkpoint=is_test,
        )
        return agent_app.stream(db=db, req=agent_req, req_ctx=req_ctx, request_type=request_type)

    if app.app_type == "rag":
        rag_req = RagRunRequest(
            app_id=app_id,
            query=_resolve_query(req),
            messages=req.messages or [],
            variables=req.variables,
        )
        # RagApp.stream 内部用独立 SessionLocal,这里入参 db 可放心关闭
        db.close()
        return rag_app.stream(db=None, req=rag_req, req_ctx=req_ctx, request_type=request_type)  # type: ignore[arg-type]

    db.close()
    raise ServiceError(
        ErrorCode.BAD_REQUEST, f"streaming not supported for app type: {app.app_type}"
    )


async def _dispatch(
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
        return await agent_app.run(db=db, req=agent_req, req_ctx=req_ctx, request_type=request_type)

    if app.app_type == "rag":
        # 多轮:把 messages 直接交给 RagApp,内部抽 last user 为 query;
        # 单轮兼容:_resolve_query 退回单条 query 字段。
        rag_req = RagRunRequest(
            app_id=app_id,
            query=_resolve_query(req),
            messages=req.messages or [],
            variables=req.variables,
        )
        return rag_app.run(
            db=db,
            req=rag_req,
            req_ctx=req_ctx,
            request_type=request_type,
        )

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
