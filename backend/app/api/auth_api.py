from fastapi import APIRouter, Depends, Response
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

# 全站鉴权 cookie:httpOnly + SameSite=Lax + Path=/。
# 既被 /flowise/* 反向代理读取,也被 build_request_context 作为主鉴权来源
# (Bearer 头仅作为 SDK/CLI 的兜底)。
EASYAI_COOKIE = "easyai_token"
EASYAI_COOKIE_PATH = "/"
EASYAI_COOKIE_MAX_AGE = 8 * 3600


@router.post("/login", response_model=Resp[UserLoginResp])
def login(
    req: UserLoginReq,
    response: Response,
    db: Session = Depends(get_db),
) -> Resp[UserLoginResp]:
    data = user_service.login(db=db, req=req)
    # 全站 httpOnly cookie:浏览器流量统一走 cookie,/flowise/* 反代亦读取它
    response.set_cookie(
        EASYAI_COOKIE,
        data.access_token,
        httponly=True,
        samesite="lax",
        path=EASYAI_COOKIE_PATH,
        max_age=EASYAI_COOKIE_MAX_AGE,
    )
    return Resp(data=data)


@router.post("/logout")
def logout(response: Response) -> Resp[None]:
    response.delete_cookie(EASYAI_COOKIE, path=EASYAI_COOKIE_PATH)
    return Resp(data=None)


@router.get("/me", response_model=Resp[UserResp])
def me(
    req_ctx: RequestContext = Depends(build_request_context),
    db: Session = Depends(get_db),
) -> Resp[UserResp]:
    if req_ctx.user_id is None:
        raise ServiceError(ErrorCode.UNAUTHORIZED, "unauthorized")
    data = user_service.get_user_by_id(db=db, user_id=req_ctx.user_id)
    return Resp(data=data)
