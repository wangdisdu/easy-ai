"""对外网关调用日志埋点。

从 request 上下文提取字段并调用 service 写一条 tb_api_access_log。
两个调用点:handlers(所有错误响应)+ invoke(成功响应)。详见
docs/application-integration-design.md §14。
"""

from __future__ import annotations

import time

from fastapi import Request

from app.api.integration_api import service as integration_service


def _safe_int(v: object) -> int | None:
    try:
        return int(v) if v is not None else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def log_access(
    request: Request,
    *,
    status_code: int,
    code: str,
    reason: str | None = None,
    error_message: str | None = None,
) -> None:
    """记录一次网关调用。

    integration_id / key_id 由 deps.integration_auth 在解析成功后写到 request.state;
    鉴权在解析之前就失败时它们为 None。app_type / app_id 取自路由 path 参数,
    路由能匹配上就一定存在。
    """
    state = request.state
    start = getattr(state, "access_start", None)
    latency_ms = int((time.perf_counter() - start) * 1000) if start is not None else None
    path_params = request.path_params
    integration_service.record_access_log(
        integration_id=getattr(state, "access_intg_id", None),
        key_id=getattr(state, "access_key_id", None),
        app_type=path_params.get("app_type"),
        app_id=_safe_int(path_params.get("app_id")),
        status_code=status_code,
        code=code,
        reason=reason,
        latency_ms=latency_ms,
        client_ip=request.client.host if request.client else None,
        request_bytes=_safe_int(request.headers.get("content-length")),
        error_message=error_message,
    )
