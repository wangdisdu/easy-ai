from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import PagedResp, Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.app_model import (
    AppCreateReq,
    AppPageReq,
    AppPublishReq,
    AppResp,
    AppUpdateReq,
    AppVersionResp,
)
from app.model.open_model import AppLogResp
from app.service.app_log_service import AppLogService
from app.service.app_service import AppService

router = APIRouter(prefix="/app", tags=["app"])
service = AppService(SnowflakeGenerator(settings.snowflake_worker_id))
app_log_service = AppLogService(SnowflakeGenerator(settings.snowflake_worker_id))


@router.get("/page", response_model=PagedResp[AppResp])
def page_app(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    keyword: str | None = Query(default=None),
    app_type: str | None = Query(default=None),
    app_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PagedResp[AppResp]:
    data, total = service.page_app(
        db=db,
        req=AppPageReq(
            page_no=page_no,
            page_size=page_size,
            keyword=keyword,
            app_type=app_type,
            app_status=app_status,
        ),
    )
    return PagedResp(data=data, total=total)


@router.post("", response_model=Resp[AppResp])
def create_app(
    req: AppCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[AppResp]:
    return Resp(data=service.create_app(db=db, req=req, req_ctx=req_ctx))


@router.get("/{app_id}", response_model=Resp[AppResp])
def get_app(app_id: str, db: Session = Depends(get_db)) -> Resp[AppResp]:
    return Resp(data=service.get_app_by_id(db=db, app_id=int(app_id)))


@router.put("/{app_id}", response_model=Resp[AppResp])
def update_app(
    app_id: str,
    req: AppUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[AppResp]:
    return Resp(data=service.update_app(db=db, app_id=int(app_id), req=req, req_ctx=req_ctx))


@router.delete("/{app_id}", response_model=Resp[bool])
def delete_app(
    app_id: str,
    req_ctx: RequestContext = Depends(build_request_context),
    db: Session = Depends(get_db),
) -> Resp[bool]:
    service.delete_app(db=db, app_id=int(app_id), req_ctx=req_ctx)
    return Resp(data=True)


@router.post("/{app_id}/publish", response_model=Resp[AppVersionResp])
def publish_app(
    app_id: str,
    req: AppPublishReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[AppVersionResp]:
    return Resp(data=service.publish_app(db=db, app_id=int(app_id), req=req, req_ctx=req_ctx))


@router.get("/{app_id}/version", response_model=Resp[list[AppVersionResp]])
def list_versions(app_id: str, db: Session = Depends(get_db)) -> Resp[list[AppVersionResp]]:
    return Resp(data=service.list_versions(db=db, app_id=int(app_id)))


@router.get("/{app_id}/log", response_model=Resp[list[AppLogResp]])
def list_app_logs(
    app_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> Resp[list[AppLogResp]]:
    return Resp(data=app_log_service.list_app_logs(db=db, app_id=int(app_id), limit=limit))


@router.post("/{app_id}/offline", response_model=Resp[AppResp])
def offline_app(
    app_id: str,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[AppResp]:
    return Resp(data=service.offline_app(db=db, app_id=int(app_id), req_ctx=req_ctx))
