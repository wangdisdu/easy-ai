import time

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbUser, TbUserGroup, TbUserGroupMember
from app.model.user_model import UserResp
from app.model.user_group_model import (
    UserGroupCreateReq,
    UserGroupMemberResp,
    UserGroupPageReq,
    UserGroupResp,
    UserGroupUpdateReq,
)


class UserGroupService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator

    def create_group(
        self, db: Session, req: UserGroupCreateReq, req_ctx: RequestContext
    ) -> UserGroupResp:
        existing = db.scalar(select(TbUserGroup).where(TbUserGroup.code == req.code))
        if existing:
            raise ServiceError(ErrorCode.DATA_DUPLICATE, "group code already exists")

        now = req_ctx.request_time_ms
        group = TbUserGroup(
            id=self._id_generator.next_id(),
            code=req.code,
            name=req.name,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(group)
        db.commit()
        db.refresh(group)
        return UserGroupResp.from_entity(group)

    def page_user_group(
        self, db: Session, req: UserGroupPageReq
    ) -> tuple[list[UserGroupResp], int]:
        stmt = select(TbUserGroup)
        count_stmt = select(func.count(TbUserGroup.id))
        if req.keyword:
            keyword = f"%{req.keyword}%"
            condition = or_(TbUserGroup.code.like(keyword), TbUserGroup.name.like(keyword))
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        total = db.scalar(count_stmt) or 0
        offset = (req.page_no - 1) * req.page_size
        rows = db.scalars(
            stmt.order_by(TbUserGroup.create_time.desc()).offset(offset).limit(req.page_size)
        ).all()
        return [UserGroupResp.from_entity(row) for row in rows], total

    def get_user_group_by_id(self, db: Session, group_id: int) -> UserGroupResp:
        group = db.get(TbUserGroup, group_id)
        if not group:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "group not found")
        return UserGroupResp.from_entity(group)

    def update_user_group(
        self, db: Session, group_id: int, req: UserGroupUpdateReq, req_ctx: RequestContext
    ) -> UserGroupResp:
        group = db.get(TbUserGroup, group_id)
        if not group:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "group not found")
        group.name = req.name
        group.update_time = req_ctx.request_time_ms
        group.update_user = req_ctx.user_id
        db.commit()
        db.refresh(group)
        return UserGroupResp.from_entity(group)

    def delete_user_group(self, db: Session, group_id: int) -> None:
        group = db.get(TbUserGroup, group_id)
        if not group:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "group not found")
        db.query(TbUserGroupMember).filter(TbUserGroupMember.group_id == group_id).delete()
        db.delete(group)
        db.commit()

    def add_member(
        self, db: Session, group_id: int, user_id: int, req_ctx: RequestContext
    ) -> UserGroupMemberResp:
        if not db.get(TbUserGroup, group_id):
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "group not found")
        if not db.get(TbUser, user_id):
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "user not found")

        existing = db.scalar(
            select(TbUserGroupMember).where(
                TbUserGroupMember.group_id == group_id,
                TbUserGroupMember.user_id == user_id,
            )
        )
        if existing:
            raise ServiceError(ErrorCode.DATA_DUPLICATE, "user already in group")

        now = int(time.time() * 1000)
        member = TbUserGroupMember(
            id=self._id_generator.next_id(),
            user_id=user_id,
            group_id=group_id,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(member)
        db.commit()
        db.refresh(member)
        return UserGroupMemberResp(
            id=str(member.id),
            user_id=str(member.user_id),
            group_id=str(member.group_id),
        )

    def list_members(self, db: Session, group_id: int) -> list[UserResp]:
        if not db.get(TbUserGroup, group_id):
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "group not found")

        rows = db.scalars(
            select(TbUser)
            .join(TbUserGroupMember, TbUserGroupMember.user_id == TbUser.id)
            .where(TbUserGroupMember.group_id == group_id)
            .order_by(TbUser.create_time.desc())
        ).all()
        return [UserResp.from_entity(row) for row in rows]

    def remove_member(self, db: Session, group_id: int, user_id: int) -> None:
        if not db.get(TbUserGroup, group_id):
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "group not found")

        member = db.scalar(
            select(TbUserGroupMember).where(
                TbUserGroupMember.group_id == group_id,
                TbUserGroupMember.user_id == user_id,
            )
        )
        if not member:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "group member not found")

        db.delete(member)
        db.commit()
