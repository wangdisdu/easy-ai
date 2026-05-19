"""沙盒生命周期登记表。

沙盒按会话线程(thread_id)复用:HITL 中断后 ``resume_stream()`` 会重建
agent(``agent_app._prepare`` 每次新建 backend),沙盒不能随 backend 对象
销毁,否则中断/恢复会落到不同执行环境。Registry 按 thread_id 查找复用,
并负责暖池预热与随 checkpoint purge 的联动回收。

复用范围是**进程内**:``_by_thread`` 只在当前进程有效。多 worker / 重启后
同一 thread 落到别的进程时,这里查不到句柄会新建沙盒(旧的靠 OpenSandbox
idle timeout 回收)。跨进程复用需把 sandbox_id 持久化(随 checkpoint)再用
``SandboxSync.resume`` 重连,留待多 worker 阶段(docs/sandbox-design.md §8)。

设计依据 docs/sandbox-design.md §4.2 / §7。
"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

from app.app.sandbox.opensandbox_backend import OpenSandboxBackend
from app.core.config import settings
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError

logger = logging.getLogger(__name__)

# 沙盒最长存活时间:无 idle_timeout 配置时的兜底(秒)。命令级超时是另一回事
# (RunCommandOpts.timeout,见 OpenSandboxBackend),不要混。
_DEFAULT_SANDBOX_TTL = 30 * 60
# 通用 keep-alive entrypoint:BaseSandbox 把 ls/grep/glob/read/edit 都派生成
# 往沙盒里 exec shell 命令,容器必须常驻不退出。
_KEEPALIVE_ENTRYPOINT = ["tail", "-f", "/dev/null"]
# 可视化沙盒:桌面镜像内 noVNC 网页客户端监听端口(见 deploy/opensandbox/desktop)。
_NOVNC_PORT = 6080
# 桌面镜像内置的幂等启动脚本路径。
_DESKTOP_BOOT = "/usr/local/bin/start-desktop.sh"


class SandboxRegistry:
    """进程内单例。维护 thread_id -> sandbox 句柄映射 + per-app 暖池。

    线程安全:用一把粗粒度锁保护映射表(创建/销毁低频,够用)。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # thread_id -> OpenSandbox SDK 句柄
        self._by_thread: dict[str, Any] = {}
        # app_id -> 预热的空闲句柄列表
        self._warm_pool: dict[str, list[Any]] = {}

    # -- 取/建 -----------------------------------------------------------

    def get_or_create(
        self,
        *,
        session_key: str | None,
        app_config: dict[str, Any],
    ) -> OpenSandboxBackend:
        """按 session_key(通常是 thread_id)复用沙盒。

        session_key 为空(一次性直 API,无 thread_id)时每次新建匿名沙盒,
        调用方用完应自行 ``release(backend.id)``。
        """
        if session_key:
            with self._lock:
                handle = self._by_thread.get(session_key)
            if handle is not None:
                return OpenSandboxBackend(
                    sandbox=handle,
                    sandbox_id=session_key,
                    default_timeout=self._timeout(app_config),
                )

        handle = self._create_handle(app_config)
        sandbox_id = session_key or self._handle_id(handle)
        # 匿名(一次性直 API,无 thread_id)也按 sandbox_id 登记,使
        # release(backend.id) 能回收它,而不是只靠 OpenSandbox idle timeout 兜底。
        with self._lock:
            self._by_thread[sandbox_id] = handle
        return OpenSandboxBackend(
            sandbox=handle,
            sandbox_id=sandbox_id,
            default_timeout=self._timeout(app_config),
        )

    # -- 可视化 ---------------------------------------------------------

    def desktop_endpoint(self, session_key: str) -> dict[str, Any] | None:
        """确保该会话沙盒桌面栈已起,返回 noVNC 的访问 URL(经 server 代理)。

        - 沙盒尚未创建(用户还没触发任何沙盒工具)→ 返回 None,前端提示未就绪。
        - 否则经 execd 跑镜像内置 start-desktop.sh(幂等,pgrep 守卫),再用
          ``get_endpoint`` 取到经 lifecycle server 代理的访问 URL。
        镜像须为可视化镜像(deploy/opensandbox/desktop);普通镜像没有该脚本/
        noVNC,会在 exec 处报错并向上抛。

        注:``get_signed_endpoint``(带过期 token 的签名 URL)仅 Kubernetes
        runtime 支持;docker runtime 用 ``get_endpoint``,访问控制依赖 server
        (api_key / 网络边界)。详见 docs/sandbox-design.md §9。
        """
        with self._lock:
            handle = self._by_thread.get(session_key)
        if handle is None:
            return None
        handle.commands.run(_DESKTOP_BOOT)
        ep = handle.get_endpoint(_NOVNC_PORT)
        # OpenSandbox 返回无 scheme 的 netloc+path(如 127.0.0.1:8090/sandboxes/.../proxy/6080),
        # 浏览器 iframe 需要完整 URL;scheme 取 sandbox_server_url 的。
        raw = str(ep.endpoint)
        if "://" not in raw:
            scheme = urlparse(settings.sandbox_server_url).scheme or "http"
            raw = f"{scheme}://{raw}"
        return {"url": raw, "headers": dict(ep.headers or {})}

    def exec_in_session(self, session_key: str, command: str, *, timeout: int = 60) -> Any | None:
        """在该会话已存在的沙盒里跑一条命令(computer-use 工具用)。

        沙盒不存在 → None;否则复用 OpenSandboxBackend.execute,返回
        ExecuteResponse(output / exit_code)。
        """
        with self._lock:
            handle = self._by_thread.get(session_key)
        if handle is None:
            return None
        return OpenSandboxBackend(sandbox=handle, sandbox_id=session_key).execute(
            command, timeout=timeout
        )

    # -- 回收 -----------------------------------------------------------

    def release(self, session_key: str) -> None:
        """会话正常结束/异常时调用,kill 并移除沙盒。"""
        with self._lock:
            handle = self._by_thread.pop(session_key, None)
        if handle is None:
            return
        self._kill_handle(handle)
        logger.info("[sandbox] released session=%s", session_key)

    def purge_hook(self, session_key: str) -> None:
        """checkpoint purge 后台任务回调:thread_id 的 checkpoint 被清理时
        联动回收对应沙盒,避免泄漏。语义上等同 release,单列以便挂到
        purge 流程(见 docs/checkpoint-monitoring.md)。"""
        self.release(session_key)

    # -- 暖池 -----------------------------------------------------------

    def prewarm(self, app_id: str, app_config: dict[str, Any], count: int = 1) -> None:
        """为指定 app 预创建空闲沙盒,降低首个 execute 的冷启动延迟。

        留待暖池阶段(docs/sandbox-design.md §8 步骤 6)。当前 no-op,不影响
        按需创建路径。
        """
        _ = (app_id, app_config, count)

    # -- 内部:与 OpenSandbox SDK 交互 ----------------------------------

    def _connection_config(self) -> Any:
        from opensandbox.config import ConnectionConfigSync

        parsed = urlparse(settings.sandbox_server_url)
        return ConnectionConfigSync(
            domain=parsed.netloc or parsed.path,
            protocol=(parsed.scheme or "http"),
            api_key=settings.sandbox_api_key,
            # 关键:经 lifecycle server 代理访问沙盒,而不是直连沙盒容器 IP/端口。
            # easy-ai 部署里 backend 只能到 server(compose 网络/宿主端口),
            # 到不了临时 sandbox 的 bridge IP;不开这个会 SandboxReadyTimeout。
            use_server_proxy=True,
        )

    def _create_handle(self, app_config: dict[str, Any]) -> Any:
        if not settings.sandbox_enabled:
            raise ServiceError(
                ErrorCode.BAD_REQUEST,
                "应用配置了沙盒后端,但平台未启用沙盒(settings.sandbox_enabled=False"
                " / OpenSandbox 未部署)。详见 docs/sandbox-design.md §7。",
            )
        from opensandbox.sync import SandboxSync

        sandbox_cfg = app_config.get("sandbox") or {}
        # image 已由 agent_app._prepare 经 SandboxImageService 从 app 选的
        # image_id 解析注入;为空则交给 OpenSandbox 部署默认镜像。
        image = sandbox_cfg.get("image")
        ttl_seconds = int(sandbox_cfg.get("idle_timeout") or _DEFAULT_SANDBOX_TTL)
        resource = sandbox_cfg.get("resources") or None
        env = sandbox_cfg.get("env") or None
        # 注:网络隔离(egress_allow → NetworkPolicy)待后续接入,
        # 见 docs/sandbox-design.md §5 / §8。
        return SandboxSync.create(
            image,
            connection_config=self._connection_config(),
            timeout=timedelta(seconds=ttl_seconds),
            entrypoint=_KEEPALIVE_ENTRYPOINT,
            resource=resource,
            env=env,
            metadata={"source": "easy-ai"},
        )

    def _kill_handle(self, handle: Any) -> None:
        try:
            handle.kill()
        except Exception:
            # 回收尽力而为:kill 失败也别影响会话收尾,OpenSandbox idle
            # timeout 会兜底。
            logger.exception("[sandbox] kill failed id=%s", self._handle_id(handle))

    def _handle_id(self, handle: Any) -> str:
        return str(getattr(handle, "id", "unknown"))

    @staticmethod
    def _timeout(app_config: dict[str, Any]) -> int:
        sandbox_cfg = app_config.get("sandbox") or {}
        return int(sandbox_cfg.get("execute_timeout") or 300)


_registry: SandboxRegistry | None = None
_registry_lock = threading.Lock()


def get_sandbox_registry() -> SandboxRegistry:
    """进程内单例访问器。"""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = SandboxRegistry()
    return _registry
