import time

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.security import create_access_token, hash_password, verify_password
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbUser
from app.model.user_model import (
    UserCreateReq,
    UserPageReq,
    UserLoginReq,
    UserLoginResp,
    UserResetPasswordReq,
    UserResp,
    UserUpdateReq,
)


class UserService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator

    def create_user(
        self,
        db: Session,
        req: UserCreateReq,
        req_ctx: RequestContext,
    ) -> UserResp:
        existing = db.scalar(select(TbUser).where(TbUser.account == req.account))
        if existing:
            raise ServiceError(ErrorCode.DATA_DUPLICATE, "account already exists")

        now = int(time.time() * 1000)
        user = TbUser(
            id=self._id_generator.next_id(),
            account=req.account,
            passwd=hash_password(req.passwd),
            email=req.email,
            name=req.name,
            phone=req.phone,
            department=req.department,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return UserResp.from_entity(user)

    def page_user(self, db: Session, req: UserPageReq) -> tuple[list[UserResp], int]:
        stmt = select(TbUser)
        count_stmt = select(func.count(TbUser.id))
        if req.keyword:
            keyword = f"%{req.keyword}%"
            condition = or_(
                TbUser.account.like(keyword),
                TbUser.name.like(keyword),
                TbUser.email.like(keyword),
                TbUser.phone.like(keyword),
            )
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        total = db.scalar(count_stmt) or 0
        offset = (req.page_no - 1) * req.page_size
        rows = db.scalars(
            stmt.order_by(TbUser.create_time.desc()).offset(offset).limit(req.page_size)
        ).all()
        return [UserResp.from_entity(row) for row in rows], total

    def get_user_by_id(self, db: Session, user_id: int) -> UserResp:
        user = db.get(TbUser, user_id)
        if not user:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "user not found")
        return UserResp.from_entity(user)

    def update_user(
        self, db: Session, user_id: int, req: UserUpdateReq, req_ctx: RequestContext
    ) -> UserResp:
        user = db.get(TbUser, user_id)
        if not user:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "user not found")

        if req.email is not None:
            user.email = req.email
        if req.name is not None:
            user.name = req.name
        if req.phone is not None:
            user.phone = req.phone
        if req.department is not None:
            user.department = req.department
        user.update_time = req_ctx.request_time_ms
        user.update_user = req_ctx.user_id

        db.commit()
        db.refresh(user)
        return UserResp.from_entity(user)

    def delete_user(self, db: Session, user_id: int) -> None:
        user = db.get(TbUser, user_id)
        if not user:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "user not found")
        db.delete(user)
        db.commit()

    def reset_password(
        self, db: Session, user_id: int, req: UserResetPasswordReq, req_ctx: RequestContext
    ) -> None:
        user = db.get(TbUser, user_id)
        if not user:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "user not found")
        user.passwd = hash_password(req.new_passwd)
        user.update_time = req_ctx.request_time_ms
        user.update_user = req_ctx.user_id
        db.commit()

    def login(self, db: Session, req: UserLoginReq) -> UserLoginResp:
        user = db.scalar(select(TbUser).where(TbUser.account == req.account))
        if not user or not verify_password(req.passwd, user.passwd):
            raise ServiceError(ErrorCode.UNAUTHORIZED, "account or password invalid")
        token = create_access_token(user.id)
        return UserLoginResp(access_token=token, user=UserResp.from_entity(user))
