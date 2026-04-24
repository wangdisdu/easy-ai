from __future__ import annotations

from typing import Any

from deepagents.backends import StateBackend
from deepagents.backends.protocol import BackendProtocol

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError


class BackendFactory:
    """构造 DeepAgents backend。

    集中 backend 选择，方便未来接入 OpenSandbox 等沙盒后端：新增一类 backend 只
    需扩展 create，不用改 AgentApp。
    """

    def create(self, app_config: dict[str, Any] | None = None) -> BackendProtocol:
        config = app_config or {}
        backend_type = str(config.get("runtime_backend") or "state").lower()
        if backend_type == "state":
            return StateBackend()
        raise ServiceError(
            ErrorCode.BAD_REQUEST,
            f"unsupported runtime backend: {backend_type}",
        )
