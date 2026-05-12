from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import PagedResp, Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.app_category_model import (
    AppCategoryCreateReq,
    AppCategoryPageReq,
    AppCategoryResp,
    AppCategoryUpdateReq,
)
from app.service.app_category_service import AppCategoryService

router = APIRouter(prefix="/app-category", tags=["app-category"])
service = AppCategoryService(SnowflakeGenerator(settings.snowflake_worker_id))


@router.get("/page", response_model=PagedResp[AppCategoryResp])
def page_category(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PagedResp[AppCategoryResp]:
    data, total = service.page_category(
        db=db,
        req=AppCategoryPageReq(page_no=page_no, page_size=page_size, keyword=keyword),
    )
    return PagedResp(data=data, total=total)


@router.get("/list", response_model=Resp[list[AppCategoryResp]])
def list_category(db: Session = Depends(get_db)) -> Resp[list[AppCategoryResp]]:
    return Resp(data=service.list_all(db=db))


@router.post("", response_model=Resp[AppCategoryResp])
def create_category(
    req: AppCategoryCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[AppCategoryResp]:
    return Resp(data=service.create_category(db=db, req=req, req_ctx=req_ctx))


@router.get("/{category_id}", response_model=Resp[AppCategoryResp])
def get_category(category_id: str, db: Session = Depends(get_db)) -> Resp[AppCategoryResp]:
    return Resp(data=service.get_category_by_id(db=db, category_id=int(category_id)))


@router.put("/{category_id}", response_model=Resp[AppCategoryResp])
def update_category(
    category_id: str,
    req: AppCategoryUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[AppCategoryResp]:
    return Resp(
        data=service.update_category(db=db, category_id=int(category_id), req=req, req_ctx=req_ctx)
    )


@router.delete("/{category_id}", response_model=Resp[bool])
def delete_category(category_id: str, db: Session = Depends(get_db)) -> Resp[bool]:
    service.delete_category(db=db, category_id=int(category_id))
    return Resp(data=True)
