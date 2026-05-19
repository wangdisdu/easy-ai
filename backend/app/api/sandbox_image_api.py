"""沙盒镜像配置 API(/api/v1/sandbox-image)。

平台级镜像目录,Agent 应用在 app_config.sandbox.image_id 里从中选一个作为
沙盒镜像。仅声明端点;逻辑在 ``SandboxImageService``。详见 docs/sandbox-design.md §7。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import PagedResp, Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.sandbox_model import (
    SandboxImageCreateReq,
    SandboxImagePageReq,
    SandboxImageResp,
    SandboxImageUpdateReq,
)
from app.service.sandbox_image_service import SandboxImageService

router = APIRouter(prefix="/sandbox-image", tags=["sandbox-image"])
service = SandboxImageService(SnowflakeGenerator(settings.snowflake_worker_id))


@router.get("/page", response_model=PagedResp[SandboxImageResp])
def page_image(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PagedResp[SandboxImageResp]:
    data, total = service.page_image(
        db=db,
        req=SandboxImagePageReq(page_no=page_no, page_size=page_size, keyword=keyword),
    )
    return PagedResp(data=data, total=total)


@router.get("/list", response_model=Resp[list[SandboxImageResp]])
def list_image(db: Session = Depends(get_db)) -> Resp[list[SandboxImageResp]]:
    """供应用配置下拉选择:只返回启用的镜像。"""
    return Resp(data=service.list_enabled(db=db))


@router.post("", response_model=Resp[SandboxImageResp])
def create_image(
    req: SandboxImageCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[SandboxImageResp]:
    return Resp(data=service.create_image(db=db, req=req, req_ctx=req_ctx))


@router.get("/{image_id}", response_model=Resp[SandboxImageResp])
def get_image(image_id: str, db: Session = Depends(get_db)) -> Resp[SandboxImageResp]:
    return Resp(data=service.get_image_by_id(db=db, image_id=int(image_id)))


@router.put("/{image_id}", response_model=Resp[SandboxImageResp])
def update_image(
    image_id: str,
    req: SandboxImageUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[SandboxImageResp]:
    return Resp(data=service.update_image(db=db, image_id=int(image_id), req=req, req_ctx=req_ctx))


@router.delete("/{image_id}", response_model=Resp[bool])
def delete_image(image_id: str, db: Session = Depends(get_db)) -> Resp[bool]:
    service.delete_image(db=db, image_id=int(image_id))
    return Resp(data=True)
