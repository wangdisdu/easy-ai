from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext, build_request_context
from app.core.response import PagedResp, Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.role_model import RoleCreateReq, RolePageReq, RoleResp, RoleUpdateReq, UserRoleAddReq
from app.model.user_model import UserResp
from app.service.role_service import RoleService

router = APIRouter(prefix="/role", tags=["role"])
service = RoleService(SnowflakeGenerator(settings.snowflake_worker_id))


@router.get("/page", response_model=PagedResp[RoleResp])
def page_role(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    keyword: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PagedResp[RoleResp]:
    data, total = service.page_role(
        db=db, req=RolePageReq(page_no=page_no, page_size=page_size, keyword=keyword)
    )
    return PagedResp(data=data, total=total)


@router.post("", response_model=Resp[RoleResp])
def create_role(
    req: RoleCreateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[RoleResp]:
    return Resp(data=service.create_role(db=db, req=req, req_ctx=req_ctx))


@router.get("", response_model=Resp[list[RoleResp]])
def list_role(db: Session = Depends(get_db)) -> Resp[list[RoleResp]]:
    return Resp(data=service.list_role(db=db))


@router.get("/{role_id}", response_model=Resp[RoleResp])
def get_role(role_id: str, db: Session = Depends(get_db)) -> Resp[RoleResp]:
    return Resp(data=service.get_role_by_id(db=db, role_id=int(role_id)))


@router.put("/{role_id}", response_model=Resp[RoleResp])
def update_role(
    role_id: str,
    req: RoleUpdateReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[RoleResp]:
    return Resp(data=service.update_role(db=db, role_id=int(role_id), req=req, req_ctx=req_ctx))


@router.delete("/{role_id}", response_model=Resp[bool])
def delete_role(role_id: str, db: Session = Depends(get_db)) -> Resp[bool]:
    service.delete_role(db=db, role_id=int(role_id))
    return Resp(data=True)


@router.post("/{role_id}/user", response_model=Resp[bool])
def bind_user_role(
    role_id: str,
    req: UserRoleAddReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[bool]:
    service.bind_role_to_user(
        db=db, role_id=int(role_id), user_id=int(req.user_id), req_ctx=req_ctx
    )
    return Resp(data=True)


@router.get("/{role_id}/user", response_model=Resp[list[UserResp]])
def list_role_users(role_id: str, db: Session = Depends(get_db)) -> Resp[list[UserResp]]:
    return Resp(data=service.list_users_by_role(db=db, role_id=int(role_id)))
