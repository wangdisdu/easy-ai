import json
import time

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbRole, TbUser, TbUserRole
from app.model.role_model import RoleCreateReq, RolePageReq, RoleResp, RoleUpdateReq
from app.model.user_model import UserResp


class RoleService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator

    def create_role(self, db: Session, req: RoleCreateReq, req_ctx: RequestContext) -> RoleResp:
        existing = db.scalar(select(TbRole).where(TbRole.code == req.code))
        if existing:
            raise ServiceError(ErrorCode.DATA_DUPLICATE, "role code already exists")
        now = req_ctx.request_time_ms
        role = TbRole(
            id=self._id_generator.next_id(),
            code=req.code,
            name=req.name,
            permissions=json.dumps(req.permissions, ensure_ascii=False),
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(role)
        db.commit()
        db.refresh(role)
        return RoleResp.from_entity(role, req.permissions)

    def list_role(self, db: Session) -> list[RoleResp]:
        rows = db.scalars(select(TbRole).order_by(TbRole.create_time.desc())).all()
        result: list[RoleResp] = []
        for row in rows:
            permissions = json.loads(row.permissions) if row.permissions else []
            result.append(RoleResp.from_entity(row, permissions))
        return result

    def page_role(self, db: Session, req: RolePageReq) -> tuple[list[RoleResp], int]:
        stmt = select(TbRole)
        count_stmt = select(func.count(TbRole.id))
        if req.keyword:
            keyword = f"%{req.keyword}%"
            condition = or_(TbRole.code.like(keyword), TbRole.name.like(keyword))
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)
        total = db.scalar(count_stmt) or 0
        offset = (req.page_no - 1) * req.page_size
        rows = db.scalars(
            stmt.order_by(TbRole.create_time.desc()).offset(offset).limit(req.page_size)
        ).all()
        result: list[RoleResp] = []
        for row in rows:
            permissions = json.loads(row.permissions) if row.permissions else []
            result.append(RoleResp.from_entity(row, permissions))
        return result, total

    def get_role_by_id(self, db: Session, role_id: int) -> RoleResp:
        role = db.get(TbRole, role_id)
        if not role:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "role not found")
        permissions = json.loads(role.permissions) if role.permissions else []
        return RoleResp.from_entity(role, permissions)

    def update_role(
        self, db: Session, role_id: int, req: RoleUpdateReq, req_ctx: RequestContext
    ) -> RoleResp:
        role = db.get(TbRole, role_id)
        if not role:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "role not found")
        role.name = req.name
        role.permissions = json.dumps(req.permissions, ensure_ascii=False)
        role.update_time = req_ctx.request_time_ms
        role.update_user = req_ctx.user_id
        db.commit()
        db.refresh(role)
        return RoleResp.from_entity(role, req.permissions)

    def delete_role(self, db: Session, role_id: int) -> None:
        role = db.get(TbRole, role_id)
        if not role:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "role not found")
        db.query(TbUserRole).filter(TbUserRole.role_id == role_id).delete()
        db.delete(role)
        db.commit()

    def bind_role_to_user(
        self, db: Session, role_id: int, user_id: int, req_ctx: RequestContext
    ) -> None:
        if not db.get(TbRole, role_id):
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "role not found")
        if not db.get(TbUser, user_id):
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "user not found")

        existing = db.scalar(
            select(TbUserRole).where(
                TbUserRole.user_id == user_id,
                TbUserRole.role_id == role_id,
            )
        )
        if existing:
            raise ServiceError(ErrorCode.DATA_DUPLICATE, "user already has role")

        now = int(time.time() * 1000)
        entity = TbUserRole(
            id=self._id_generator.next_id(),
            user_id=user_id,
            role_id=role_id,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(entity)
        db.commit()

    def list_users_by_role(self, db: Session, role_id: int) -> list[UserResp]:
        if not db.get(TbRole, role_id):
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "role not found")

        rows = db.scalars(
            select(TbUser)
            .join(TbUserRole, TbUserRole.user_id == TbUser.id)
            .where(TbUserRole.role_id == role_id)
            .order_by(TbUser.create_time.desc())
        ).all()
        return [UserResp.from_entity(row) for row in rows]
