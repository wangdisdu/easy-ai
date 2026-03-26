from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import PagedResp, Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.user_group_model import (
    UserGroupCreateReq,
    UserGroupMemberAddReq,
    UserGroupMemberResp,
    UserGroupPageReq,
    UserGroupResp,
    UserGroupUpdateReq,
)
from app.service.user_group_service import UserGroupService

router = APIRouter(prefix="/user-group", tags=["user-group"])
service = UserGroupService(SnowflakeGenerator(settings.snowflake_worker_id))


@router.get("/page", response_model=PagedResp[UserGroupResp])
def page_user_group(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PagedResp[UserGroupResp]:
    data, total = service.page_user_group(
        db=db, req=UserGroupPageReq(page_no=page_no, page_size=page_size, keyword=keyword)
    )
    return PagedResp(data=data, total=total)


@router.post("", response_model=Resp[UserGroupResp])
def create_user_group(
    req: UserGroupCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[UserGroupResp]:
    return Resp(data=service.create_group(db=db, req=req, req_ctx=req_ctx))


@router.get("/{group_id}", response_model=Resp[UserGroupResp])
def get_user_group(group_id: str, db: Session = Depends(get_db)) -> Resp[UserGroupResp]:
    return Resp(data=service.get_user_group_by_id(db=db, group_id=int(group_id)))


@router.put("/{group_id}", response_model=Resp[UserGroupResp])
def update_user_group(
    group_id: str,
    req: UserGroupUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[UserGroupResp]:
    data = service.update_user_group(db=db, group_id=int(group_id), req=req, req_ctx=req_ctx)
    return Resp(data=data)


@router.delete("/{group_id}", response_model=Resp[bool])
def delete_user_group(group_id: str, db: Session = Depends(get_db)) -> Resp[bool]:
    service.delete_user_group(db=db, group_id=int(group_id))
    return Resp(data=True)


@router.post("/{group_id}/member", response_model=Resp[UserGroupMemberResp])
def add_user_group_member(
    group_id: str,
    req: UserGroupMemberAddReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[UserGroupMemberResp]:
    data = service.add_member(
        db=db, group_id=int(group_id), user_id=int(req.user_id), req_ctx=req_ctx
    )
    return Resp(data=data)
