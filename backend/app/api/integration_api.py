"""应用集成管理 API。

走主仓约定 HTTP 200 + 业务 `code`,挂在 /api/v1/integration 下,登录态保护
由 router.py 的 `_login_required` 统一加。对外网关 /open/v1/* 在 open_gateway/。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import PagedResp, Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.integration_model import (
    ApiAccessLogPageReq,
    ApiAccessLogResp,
    IntegrationCreateReq,
    IntegrationCreateResp,
    IntegrationKeyPlaintextResp,
    IntegrationKeyResp,
    IntegrationKeyUpdateReq,
    IntegrationPageReq,
    IntegrationResp,
    IntegrationStatusReq,
    IntegrationUpdateReq,
)
from app.service.integration_service import IntegrationService

router = APIRouter(prefix="/integration", tags=["integration"])
service = IntegrationService(SnowflakeGenerator(settings.snowflake_worker_id))


@router.get("/page", response_model=PagedResp[IntegrationResp])
def page_integration(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(active|disabled)$"),
    db: Session = Depends(get_db),
) -> PagedResp[IntegrationResp]:
    data, total = service.page_integration(
        db=db,
        req=IntegrationPageReq(
            page_no=page_no, page_size=page_size, keyword=keyword, status=status
        ),
    )
    return PagedResp(data=data, total=total)


@router.post("", response_model=Resp[IntegrationCreateResp])
def create_integration(
    req: IntegrationCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[IntegrationCreateResp]:
    return Resp(data=service.create_integration(db=db, req=req, req_ctx=req_ctx))


@router.get("/log/page", response_model=PagedResp[ApiAccessLogResp])
def page_access_log(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    integration_id: str | None = Query(default=None),
    only_failed: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> PagedResp[ApiAccessLogResp]:
    data, total = service.page_access_log(
        db=db,
        req=ApiAccessLogPageReq(
            page_no=page_no,
            page_size=page_size,
            integration_id=integration_id,
            only_failed=only_failed,
        ),
    )
    return PagedResp(data=data, total=total)


@router.get("/{intg_id}", response_model=Resp[IntegrationResp])
def get_integration(intg_id: str, db: Session = Depends(get_db)) -> Resp[IntegrationResp]:
    return Resp(data=service.get_integration(db=db, intg_id=int(intg_id)))


@router.put("/{intg_id}", response_model=Resp[IntegrationResp])
def update_integration(
    intg_id: str,
    req: IntegrationUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[IntegrationResp]:
    return Resp(
        data=service.update_integration(db=db, intg_id=int(intg_id), req=req, req_ctx=req_ctx)
    )


@router.delete("/{intg_id}", response_model=Resp[bool])
def delete_integration(
    intg_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[bool]:
    service.delete_integration(db=db, intg_id=int(intg_id), req_ctx=req_ctx)
    return Resp(data=True)


@router.put("/{intg_id}/status", response_model=Resp[IntegrationResp])
def set_status(
    intg_id: str,
    req: IntegrationStatusReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[IntegrationResp]:
    return Resp(
        data=service.set_status(db=db, intg_id=int(intg_id), status=req.status, req_ctx=req_ctx)
    )


@router.post("/{intg_id}/key", response_model=Resp[IntegrationKeyPlaintextResp])
def create_key(
    intg_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[IntegrationKeyPlaintextResp]:
    return Resp(data=service.create_key(db=db, intg_id=int(intg_id), req_ctx=req_ctx))


@router.put("/{intg_id}/key/{kid}", response_model=Resp[IntegrationKeyResp])
def update_key(
    intg_id: str,
    kid: str,
    req: IntegrationKeyUpdateReq,
    db: Session = Depends(get_db),
) -> Resp[IntegrationKeyResp]:
    return Resp(data=service.update_key(db=db, intg_id=int(intg_id), key_id=int(kid), req=req))


@router.post("/{intg_id}/key/{kid}/reset", response_model=Resp[IntegrationKeyPlaintextResp])
def reset_key(
    intg_id: str,
    kid: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[IntegrationKeyPlaintextResp]:
    return Resp(
        data=service.reset_key(db=db, intg_id=int(intg_id), key_id=int(kid), req_ctx=req_ctx)
    )


@router.delete("/{intg_id}/key/{kid}", response_model=Resp[bool])
def delete_key(
    intg_id: str,
    kid: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[bool]:
    service.delete_key(db=db, intg_id=int(intg_id), key_id=int(kid), req_ctx=req_ctx)
    return Resp(data=True)
