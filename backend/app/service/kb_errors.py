"""KB 服务层共用的上游错误翻译。

把 ``RagflowClientError`` / ``RagflowAuthError`` 翻译成 ``ServiceError`` 时
按错误码区分,便于前端按场景给出针对性提示(详见 ``docs/knowledge-rag-
integration-design.md`` §9):

- ``UPSTREAM_AUTH_FAILED`` — trusted-header 校验失败, 一般是 SHARED_SECRET 配置错;
  前端提示运维"测试连接 → 检查密钥"。
- ``UPSTREAM_RAGFLOW_ERROR`` — 上游 5xx / 网络 / 业务码非 0; 前端按通用 retry 处理。
"""

from __future__ import annotations

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.integration import ragflow_client


def to_service_error(e: ragflow_client.RagflowClientError, op: str) -> ServiceError:
    """统一翻译: RagflowAuthError → UPSTREAM_AUTH_FAILED, 其它 → UPSTREAM_RAGFLOW_ERROR。"""
    if isinstance(e, ragflow_client.RagflowAuthError):
        return ServiceError(
            ErrorCode.UPSTREAM_AUTH_FAILED,
            f"ragflow auth failed during {op}: {e}",
        )
    return ServiceError(
        ErrorCode.UPSTREAM_RAGFLOW_ERROR,
        f"ragflow {op} failed: {e}",
    )
