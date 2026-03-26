from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import PagedResp, Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.user_model import (
    UserCreateReq,
    UserPageReq,
    UserResetPasswordReq,
    UserResp,
    UserUpdateReq,
)
from app.service.user_service import UserService

router = APIRouter(prefix="/user", tags=["user"])
user_service = UserService(SnowflakeGenerator(settings.snowflake_worker_id))


@router.get("/page", response_model=PagedResp[UserResp])
def page_user(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PagedResp[UserResp]:
    data, total = user_service.page_user(
        db=db, req=UserPageReq(page_no=page_no, page_size=page_size, keyword=keyword)
    )
    return PagedResp(data=data, total=total)


@router.post("", response_model=Resp[UserResp])
def create_user(
    req: UserCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[UserResp]:
    user = user_service.create_user(db=db, req=req, req_ctx=req_ctx)
    return Resp(data=user)


@router.get("/{user_id}", response_model=Resp[UserResp])
def get_user(user_id: str, db: Session = Depends(get_db)) -> Resp[UserResp]:
    user = user_service.get_user_by_id(db, int(user_id))
    return Resp(data=user)


@router.put("/{user_id}", response_model=Resp[UserResp])
def update_user(
    user_id: str,
    req: UserUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[UserResp]:
    user = user_service.update_user(db=db, user_id=int(user_id), req=req, req_ctx=req_ctx)
    return Resp(data=user)


@router.delete("/{user_id}", response_model=Resp[bool])
def delete_user(user_id: str, db: Session = Depends(get_db)) -> Resp[bool]:
    user_service.delete_user(db=db, user_id=int(user_id))
    return Resp(data=True)


@router.post("/{user_id}/reset-password", response_model=Resp[bool])
def reset_password(
    user_id: str,
    req: UserResetPasswordReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[bool]:
    user_service.reset_password(db=db, user_id=int(user_id), req=req, req_ctx=req_ctx)
    return Resp(data=True)
