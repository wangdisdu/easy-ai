import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.response import Resp

logger = logging.getLogger(__name__)


def _format_validation_message(exc: RequestValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = err.get("loc") or ()
        tail = [str(x) for x in loc if x not in ("body", "query", "path")]
        field = ".".join(tail) if tail else "request"
        msg = err.get("msg") or "invalid value"
        parts.append(f"{field}: {msg}")
    if not parts:
        return "参数校验失败"
    return f"参数校验失败({'; '.join(parts)})"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        msg = _format_validation_message(exc)
        resp = Resp(code=ErrorCode.VALIDATION_FAILED, msg=msg)
        return JSONResponse(status_code=200, content=resp.model_dump())

    @app.exception_handler(ServiceError)
    async def handle_service_error(_: Request, exc: ServiceError) -> JSONResponse:
        if exc.cause is not None:
            logger.exception("service error: %s", exc.msg, exc_info=exc.cause)
        resp = Resp(code=exc.code, msg=exc.msg)
        return JSONResponse(status_code=200, content=resp.model_dump())

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, __: Exception) -> JSONResponse:
        resp = Resp(code=ErrorCode.INTERNAL_ERROR, msg="internal server error")
        return JSONResponse(status_code=200, content=resp.model_dump())
