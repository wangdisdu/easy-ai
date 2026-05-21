"""对外网关 /open/v1/* 专用异常。

与 ServiceError 区分:ServiceError 走全局 handler 统一返回 HTTP 200 + 业务 code;
本异常携带 status_code/headers/extra,由 open_gateway 的独立 handler 转成标准
HTTP 4xx/5xx 响应。详见 docs/application-integration-design.md §12.2。
"""

from __future__ import annotations


class IntegrationApiError(Exception):
    """对外网关错误。

    `code` 用字符串枚举(`API_KEY_INVALID` 等),直接进响应体的 `code` 字段,
    与 HTTP status code 各司其职。`headers` 用于挂 `Retry-After` 和
    `X-RateLimit-*`。`extra` 是会合并进响应体的附加字段(如 `reason`)。
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
        extra: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers or {}
        self.extra = extra or {}
