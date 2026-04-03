import time
from collections import defaultdict

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.security import create_access_token, hash_password, verify_password
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbRole, TbUser, TbUserRole
from app.model.user_model import (
    UserCreateReq,
    UserLoginReq,
    UserLoginResp,
    UserPageReq,
    UserResetPasswordReq,
    UserResp,
    UserRoleResp,
    UserUpdateReq,
)


class UserService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator

    def _parse_role_ids(self, role_ids: list[str]) -> list[int]:
        try:
            parsed = [int(role_id) for role_id in role_ids]
        except (TypeError, ValueError) as exc:
            raise ServiceError(ErrorCode.BAD_REQUEST, "role id invalid") from exc
        return list(dict.fromkeys(parsed))

    def _load_user_roles(self, db: Session, user_ids: list[int]) -> dict[int, list[UserRoleResp]]:
        role_map: dict[int, list[UserRoleResp]] = defaultdict(list)
        if not user_ids:
            return role_map

        rows = db.execute(
            select(TbUserRole.user_id, TbRole.id, TbRole.code, TbRole.name)
            .join(TbRole, TbRole.id == TbUserRole.role_id)
            .where(TbUserRole.user_id.in_(user_ids))
            .order_by(TbRole.create_time.desc())
        ).all()
        for user_id, role_id, role_code, role_name in rows:
            role_map[user_id].append(UserRoleResp(id=str(role_id), code=role_code, name=role_name))
        return role_map

    def _sync_user_roles(
        self,
        db: Session,
        user_id: int,
        role_ids: list[int],
        req_ctx: RequestContext,
    ) -> None:
        existing_roles = {
            role.id for role in db.scalars(select(TbRole).where(TbRole.id.in_(role_ids))).all()
        }
        missing_role_ids = [role_id for role_id in role_ids if role_id not in existing_roles]
        if missing_role_ids:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "role not found")

        existing_bindings = db.scalars(
            select(TbUserRole).where(TbUserRole.user_id == user_id)
        ).all()
        existing_role_ids = {binding.role_id for binding in existing_bindings}

        for binding in existing_bindings:
            if binding.role_id not in role_ids:
                db.delete(binding)

        now = req_ctx.request_time_ms
        for role_id in role_ids:
            if role_id in existing_role_ids:
                continue
            db.add(
                TbUserRole(
                    id=self._id_generator.next_id(),
                    user_id=user_id,
                    role_id=role_id,
                    create_time=now,
                    update_time=now,
                    create_user=req_ctx.user_id,
                    update_user=req_ctx.user_id,
                )
            )

    def create_user(
        self,
        db: Session,
        req: UserCreateReq,
        req_ctx: RequestContext,
    ) -> UserResp:
        existing = db.scalar(select(TbUser).where(TbUser.account == req.account))
        if existing:
            raise ServiceError(ErrorCode.DATA_DUPLICATE, "account already exists")
        role_ids = self._parse_role_ids(req.role_ids)

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
        db.flush()
        if role_ids:
            self._sync_user_roles(db=db, user_id=user.id, role_ids=role_ids, req_ctx=req_ctx)
        db.commit()
        db.refresh(user)
        role_map = self._load_user_roles(db, [user.id])
        return UserResp.from_entity(user, role_map.get(user.id))

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
        role_map = self._load_user_roles(db, [row.id for row in rows])
        return [UserResp.from_entity(row, role_map.get(row.id)) for row in rows], total

    def get_user_by_id(self, db: Session, user_id: int) -> UserResp:
        user = db.get(TbUser, user_id)
        if not user:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "user not found")
        role_map = self._load_user_roles(db, [user.id])
        return UserResp.from_entity(user, role_map.get(user.id))

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

        if req.role_ids is not None:
            self._sync_user_roles(
                db=db,
                user_id=user_id,
                role_ids=self._parse_role_ids(req.role_ids),
                req_ctx=req_ctx,
            )

        db.commit()
        db.refresh(user)
        role_map = self._load_user_roles(db, [user.id])
        return UserResp.from_entity(user, role_map.get(user.id))

    def delete_user(self, db: Session, user_id: int) -> None:
        user = db.get(TbUser, user_id)
        if not user:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "user not found")
        db.query(TbUserRole).filter(TbUserRole.user_id == user_id).delete()
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
