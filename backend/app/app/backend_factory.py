from __future__ import annotations

from typing import Any

from deepagents.backends import CompositeBackend, StateBackend
from deepagents.backends.protocol import BackendProtocol

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError


class BackendFactory:
    """构造 DeepAgents backend。

    集中 backend 选择,新增一类 backend 只需扩展 create,不用改 AgentApp。
    沙盒方案详见 docs/sandbox-design.md。
    """

    def create(
        self,
        app_config: dict[str, Any] | None = None,
        *,
        session_key: str | None = None,
    ) -> BackendProtocol:
        """
        Args:
            app_config: 应用配置;``runtime_backend`` 决定后端类型。
            session_key: 会话标识(通常是 thread_id),用于沙盒按线程复用。
                state 后端忽略此参数。
        """
        config = app_config or {}
        backend_type = str(config.get("runtime_backend") or "state").lower()

        if backend_type == "state":
            return StateBackend()

        if backend_type == "opensandbox":
            return self._create_opensandbox(config, session_key)

        if backend_type == "composite":
            # /workspace/** 走沙盒(可执行),其余走 state(快、随 checkpoint 持久)。
            # 详见 docs/sandbox-design.md §6。
            sandbox = self._create_opensandbox(config, session_key)
            return CompositeBackend(
                default=StateBackend(),
                routes={"/workspace/": sandbox},
            )

        raise ServiceError(
            ErrorCode.BAD_REQUEST,
            f"unsupported runtime backend: {backend_type}",
        )

    def _create_opensandbox(
        self,
        config: dict[str, Any],
        session_key: str | None,
    ) -> BackendProtocol:
        # 延迟导入:未启用沙盒的部署不需要付出 import 代价,也避免 SDK 缺失时
        # 影响默认 state 路径。
        from app.app.sandbox import get_sandbox_registry

        return get_sandbox_registry().get_or_create(
            session_key=session_key,
            app_config=config,
        )
