"""沙盒实例运维 API(/api/v1/sandbox-instance)。

平台级运维入口:列出 OpenSandbox server 当前所有沙盒(可看到 backend 进程
丢失映射的"孤儿"),手动停止,查看 noVNC 桌面。仅声明端点;逻辑在
``SandboxInstanceService``。详见 docs/sandbox-design.md §10.2-(f)。
"""

from fastapi import APIRouter

from app.core.response import Resp
from app.model.sandbox_model import SandboxInstanceResp, SandboxViewResp
from app.service.sandbox_instance_service import SandboxInstanceService

router = APIRouter(prefix="/sandbox-instance", tags=["sandbox-instance"])
service = SandboxInstanceService()


@router.get("", response_model=Resp[list[SandboxInstanceResp]])
def list_instances() -> Resp[list[SandboxInstanceResp]]:
    return Resp(data=service.list_instances())


@router.delete("/{sandbox_id}", response_model=Resp[bool])
def kill_instance(sandbox_id: str) -> Resp[bool]:
    service.kill_instance(sandbox_id)
    return Resp(data=True)


@router.get("/{sandbox_id}/view", response_model=Resp[SandboxViewResp])
def get_instance_view(sandbox_id: str) -> Resp[SandboxViewResp]:
    return Resp(data=service.view_endpoint(sandbox_id))
