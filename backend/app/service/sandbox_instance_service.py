"""沙盒实例运维 service:列表 / 停止 / 看桌面。

直接走 OpenSandbox SDK,信息源是 lifecycle server 本身(不依赖本进程内的
SandboxRegistry),因此能看到所有沙盒(包括 backend 重启后丢失映射的"孤儿"),
并能停掉它们。详见 docs/sandbox-design.md §10.2-(f)。
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from app.core.config import settings
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.model.sandbox_model import SandboxInstanceResp, SandboxViewResp

logger = logging.getLogger(__name__)

_NOVNC_PORT = 6080
_DESKTOP_BOOT = "/usr/local/bin/start-desktop.sh"


class SandboxInstanceService:
    def _connection_config(self) -> Any:
        if not settings.sandbox_enabled:
            raise ServiceError(ErrorCode.BAD_REQUEST, "平台未启用沙盒")
        from opensandbox.config import ConnectionConfigSync

        parsed = urlparse(settings.sandbox_server_url)
        return ConnectionConfigSync(
            domain=parsed.netloc or parsed.path,
            protocol=(parsed.scheme or "http"),
            api_key=settings.sandbox_api_key,
            use_server_proxy=True,
        )

    def _manager(self) -> Any:
        from opensandbox.sync import SandboxManagerSync
        from opensandbox.sync.sandbox import AdapterFactorySync

        cfg = self._connection_config()
        factory = AdapterFactorySync(cfg)
        sbx = factory.create_sandbox_service()
        return SandboxManagerSync(sbx, cfg), sbx, cfg

    def list_instances(self) -> list[SandboxInstanceResp]:
        from opensandbox.models.sandboxes import SandboxFilter

        mgr, _, _ = self._manager()
        res = mgr.list_sandbox_infos(SandboxFilter())
        out: list[SandboxInstanceResp] = []
        for s in res.sandbox_infos or []:
            # SandboxInfo.image 是 SandboxImageSpec(image=..., auth=...),取内层 image 引用
            img = getattr(s, "image", None)
            img_str = getattr(img, "image", None) if img is not None else None
            # status 是 SandboxStatus 对象,取 state 字段(Running/Killed/Paused/...)
            st = getattr(s, "status", None)
            st_str = str(getattr(st, "state", st) or "") if st is not None else ""
            out.append(
                SandboxInstanceResp(
                    id=str(s.id),
                    status=st_str,
                    image=str(img_str) if img_str else None,
                    created_at=(
                        s.created_at.isoformat() if getattr(s, "created_at", None) else None
                    ),
                    expires_at=(
                        s.expires_at.isoformat() if getattr(s, "expires_at", None) else None
                    ),
                    metadata=dict(getattr(s, "metadata", {}) or {}),
                )
            )
        return out

    def kill_instance(self, sandbox_id: str) -> None:
        mgr, _, _ = self._manager()
        try:
            mgr.kill_sandbox(sandbox_id)
        except Exception as e:
            logger.warning("[sandbox-instance] kill failed id=%s: %s", sandbox_id, e)
            raise ServiceError(ErrorCode.BAD_REQUEST, f"停止失败: {e}") from e
        # 同时清掉本进程 registry 里若有的映射(若 id 是某 session_key 注册的)
        try:
            from app.app.sandbox import get_sandbox_registry

            get_sandbox_registry().release(sandbox_id)
        except Exception:
            pass

    def view_endpoint(self, sandbox_id: str) -> SandboxViewResp:
        """返回该沙盒的 noVNC 访问 URL。

        注:SDK 的 ``SandboxSync.resume`` 是"暂停后恢复"生命周期 API,运行中沙盒
        会报"not in a paused state",**不能**用作"按 id 重连"。这里直接走底层
        ``SandboxesSync.get_sandbox_endpoint(id, 6080, use_server_proxy)`` 拿代理
        URL,不依赖句柄。桌面是否已就绪取决于沙盒被创建时是否跑过 start-desktop.sh
        (我们 registry 路径创建的桌面沙盒已自动跑过);非桌面镜像/未启动桌面栈的
        沙盒,iframe 加载会失败,运维侧据此判断。"""
        cfg = self._connection_config()
        try:
            _, sbx, _ = self._manager()
            ep = sbx.get_sandbox_endpoint(sandbox_id, _NOVNC_PORT, cfg.use_server_proxy)
        except Exception as e:
            logger.warning("[sandbox-instance] get_endpoint failed id=%s: %s", sandbox_id, e)
            return SandboxViewResp(ready=False)
        raw = str(ep.endpoint)
        if "://" not in raw:
            scheme = urlparse(settings.sandbox_server_url).scheme or "http"
            raw = f"{scheme}://{raw}"
        return SandboxViewResp(ready=True, url=raw, headers=dict(ep.headers or {}))
