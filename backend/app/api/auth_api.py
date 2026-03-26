from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext, build_request_context
from app.core.response import Resp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.user_model import UserLoginReq, UserLoginResp, UserResp
from app.service.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])
user_service = UserService(SnowflakeGenerator(settings.snowflake_worker_id))


@router.post("/login", response_model=Resp[UserLoginResp])
def login(req: UserLoginReq, db: Session = Depends(get_db)) -> Resp[UserLoginResp]:
    data = user_service.login(db=db, req=req)
    return Resp(data=data)


@router.get("/me", response_model=Resp[UserResp])
def me(
    req_ctx: RequestContext = Depends(build_request_context),
    db: Session = Depends(get_db),
) -> Resp[UserResp]:
    if req_ctx.user_id is None:
        raise ServiceError(ErrorCode.UNAUTHORIZED, "unauthorized")
    data = user_service.get_user_by_id(db=db, user_id=req_ctx.user_id)
    return Resp(data=data)
