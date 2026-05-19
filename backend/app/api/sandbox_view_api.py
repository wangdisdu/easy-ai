"""可视化沙盒 API(/api/v1/sandbox-view)。

返回某会话(thread_id)沙盒 noVNC 桌面的签名访问 URL,前端 iframe 嵌入。
沙盒尚未创建则 ready=False。仅声明端点;逻辑在 SandboxRegistry。
详见 docs/sandbox-design.md §9。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.response import Resp
from app.model.sandbox_model import SandboxViewResp

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sandbox-view", tags=["sandbox-view"])


@router.get("", response_model=Resp[SandboxViewResp])
def get_sandbox_view(
    thread_id: str = Query(..., description="会话线程 id"),
) -> Resp[SandboxViewResp]:
    if not settings.sandbox_enabled:
        raise ServiceError(ErrorCode.BAD_REQUEST, "平台未启用沙盒")
    from app.app.sandbox import get_sandbox_registry

    try:
        info = get_sandbox_registry().desktop_endpoint(thread_id)
    except Exception as e:  # noqa: BLE001 - 桌面拉起/签名失败统一降级为未就绪
        logger.warning("[sandbox-view] desktop endpoint failed thread=%s: %s", thread_id, e)
        return Resp(data=SandboxViewResp(ready=False))
    if not info:
        return Resp(data=SandboxViewResp(ready=False))
    return Resp(
        data=SandboxViewResp(ready=True, url=info["url"], headers=info.get("headers") or {})
    )
