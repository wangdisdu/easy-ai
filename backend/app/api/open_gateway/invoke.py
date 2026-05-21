"""/open/v1/{app_type}/{app_id}/invoke 路由。

P0 dispatcher 复用 open_api 已存在的应用单例(AppRuntime + LlmApp + AgentApp +
RagApp),避免重复初始化。Dependency 链 integration_auth → app_bound →
rate_limit 已经把鉴权、绑定、限流都拦在前面,这里只关心成功路径与上游异常。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

# 借用 open_api 的应用单例,确保与平台内部调用共享 AppRuntime 状态
from app.api.open_api import agent_app, app_runtime, llm_app, rag_app
from app.api.open_gateway.access_log import log_access
from app.api.open_gateway.deps import AuthCtx, rate_limit
from app.core.integration_errors import IntegrationApiError
from app.core.request_context import RequestContext, build_request_context
from app.db.session import get_db
from app.model.open_model import (
    AgentRunRequest,
    AppRunReq,
    LlmAppRunReq,
    RagRunRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/open/v1", tags=["open-gateway"])


def _resolve_query(req: AppRunReq) -> str:
    if req.query and req.query.strip():
        return req.query.strip()
    query = req.inputs.get("query")
    if isinstance(query, str) and query.strip():
        return query.strip()
    for message in reversed(req.messages):
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


async def _dispatch(
    *, db: Session, app_type: str, app_id: int, req: AppRunReq, req_ctx: RequestContext
) -> dict[str, Any]:
    """按 URL 路径里的 app_type 分发,P0 仅 llm/agent/rag。

    `app_bound` 已确保 (integration, app_type, app_id) 绑定存在,这里不再重复
    校验。app_runtime.get_app 抛出的异常(应用不存在/未发布)统一包成 502。
    """
    if app_type == "llm":
        return llm_app.run(
            db=db,
            req=LlmAppRunReq(app_id=app_id, inputs=req.inputs, messages=req.messages),
            req_ctx=req_ctx,
            request_type="api",
        )
    if app_type == "agent":
        return await agent_app.run(
            db=db,
            req=AgentRunRequest(app_id=app_id, messages=req.messages, variables=req.variables),
            req_ctx=req_ctx,
            request_type="api",
        )
    if app_type == "rag":
        return rag_app.run(
            db=db,
            req=RagRunRequest(
                app_id=app_id,
                query=_resolve_query(req),
                messages=req.messages or [],
                variables=req.variables,
            ),
            req_ctx=req_ctx,
            request_type="api",
        )
    # SUPPORTED_APP_TYPES 已在 app_bound 拦截,理论不可达
    raise IntegrationApiError(403, "APP_NOT_BOUND", f"unsupported app_type: {app_type}")


@router.post("/{app_type}/{app_id}/invoke")
async def invoke(
    app_type: str,
    app_id: str,
    body: AppRunReq,
    request: Request,
    db: Session = Depends(get_db),
    ctx: AuthCtx = Depends(rate_limit),
    req_ctx: RequestContext = Depends(build_request_context),
) -> JSONResponse:
    # 借助 app_runtime.get_app 把 URL app_id 校验一遍:不存在或类型不匹配时
    # 视为 502 上游错误(因为绑定校验已通过,这里仍报错说明 tb_app 已被改动)
    try:
        app = app_runtime.get_app(db, int(app_id))
    except Exception as e:
        raise IntegrationApiError(502, "UPSTREAM_ERROR", f"app lookup failed: {e}") from e
    if app.app_type != app_type:
        raise IntegrationApiError(
            502,
            "UPSTREAM_ERROR",
            f"app_type mismatch: bound={app_type} actual={app.app_type}",
        )

    try:
        data = await _dispatch(
            db=db, app_type=app_type, app_id=int(app_id), req=body, req_ctx=req_ctx
        )
    except IntegrationApiError:
        raise
    except Exception as e:
        logger.exception("open gateway upstream error intg=%s app=%s", ctx.integration.id, app_id)
        raise IntegrationApiError(502, "UPSTREAM_ERROR", str(e)) from e

    # 成功路径:错误路径的日志由 IntegrationApiError handler 负责
    log_access(request, status_code=200, code="OK")
    headers = getattr(request.state, "rl_headers", {})
    return JSONResponse(content={"data": data}, headers=headers)
