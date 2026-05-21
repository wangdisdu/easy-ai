"""对外网关 IntegrationApiError 的独立 handler。

FastAPI 按异常类型最具体优先匹配,这个 handler 注册之后 IntegrationApiError
不会再被全局的 `Exception` handler 吞掉。管理 API 的 ServiceError 不受影响。
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.open_gateway.access_log import log_access
from app.core.integration_errors import IntegrationApiError

logger = logging.getLogger(__name__)


def register_open_gateway_handlers(app: FastAPI) -> None:
    @app.exception_handler(IntegrationApiError)
    async def handle_integration_api_error(
        request: Request, exc: IntegrationApiError
    ) -> JSONResponse:
        logger.info(
            "%s %s -> IntegrationApiError(status=%s, code=%s, msg=%s)",
            request.method,
            request.url.path,
            exc.status_code,
            exc.code,
            exc.message,
        )
        # 所有错误响应(401/403/429/502/400)都经过此 handler,统一在这里落日志
        reason = exc.extra.get("reason")
        log_access(
            request,
            status_code=exc.status_code,
            code=exc.code,
            reason=reason if isinstance(reason, str) else None,
            error_message=exc.message,
        )
        body: dict[str, object] = {"code": exc.code, "message": exc.message}
        body.update(exc.extra)
        return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)
