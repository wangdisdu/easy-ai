import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbRole, TbUser, TbUserGroup, TbUserGroupMember, TbUserRole
from app.db.session import SessionLocal
from app.model.user_model import UserCreateReq
from app.service.user_service import UserService

logger = logging.getLogger(__name__)

DEFAULT_ADMIN_ACCOUNT = "admin"
DEFAULT_ADMIN_PASSWD = "admin@123"
DEFAULT_ADMIN_NAME = "管理员"
DEFAULT_ADMIN_ROLE_CODE = "admin"
DEFAULT_ADMIN_ROLE_NAME = "管理员"
DEFAULT_SYSTEM_GROUP_CODE = "system"
DEFAULT_SYSTEM_GROUP_NAME = "系统用户组"
DEFAULT_ADMIN_PERMISSIONS = '["*"]'


def ensure_default_admin() -> None:
    """确保默认管理员、admin 角色、system 用户组及绑定关系存在。"""
    db: Session = SessionLocal()
    try:
        now = int(time.time() * 1000)
        ctx = RequestContext(user_id=None, client_ip=None, request_time_ms=now)
        id_generator = SnowflakeGenerator(settings.snowflake_worker_id)
        svc = UserService(id_generator)

        user = db.scalar(select(TbUser).where(TbUser.account == DEFAULT_ADMIN_ACCOUNT))
        if not user:
            svc.create_user(
                db,
                UserCreateReq(
                    account=DEFAULT_ADMIN_ACCOUNT,
                    passwd=DEFAULT_ADMIN_PASSWD,
                    name=DEFAULT_ADMIN_NAME,
                ),
                ctx,
            )
            user = db.scalar(select(TbUser).where(TbUser.account == DEFAULT_ADMIN_ACCOUNT))
            logger.info("default admin user created: %s", DEFAULT_ADMIN_ACCOUNT)
        elif user.name != DEFAULT_ADMIN_NAME:
            user.name = DEFAULT_ADMIN_NAME
            user.update_time = now
            user.update_user = None
            db.commit()

        role = db.scalar(select(TbRole).where(TbRole.code == DEFAULT_ADMIN_ROLE_CODE))
        if not role:
            role = TbRole(
                id=id_generator.next_id(),
                code=DEFAULT_ADMIN_ROLE_CODE,
                name=DEFAULT_ADMIN_ROLE_NAME,
                permissions=DEFAULT_ADMIN_PERMISSIONS,
                create_time=now,
                update_time=now,
                create_user=None,
                update_user=None,
            )
            db.add(role)
            db.commit()
            logger.info("default admin role created: %s", DEFAULT_ADMIN_ROLE_CODE)

        group = db.scalar(select(TbUserGroup).where(TbUserGroup.code == DEFAULT_SYSTEM_GROUP_CODE))
        if not group:
            group = TbUserGroup(
                id=id_generator.next_id(),
                code=DEFAULT_SYSTEM_GROUP_CODE,
                name=DEFAULT_SYSTEM_GROUP_NAME,
                create_time=now,
                update_time=now,
                create_user=None,
                update_user=None,
            )
            db.add(group)
            db.commit()
            logger.info("default system user group created: %s", DEFAULT_SYSTEM_GROUP_CODE)

        user_role = db.scalar(
            select(TbUserRole).where(TbUserRole.user_id == user.id, TbUserRole.role_id == role.id)
        )
        if not user_role:
            db.add(
                TbUserRole(
                    id=id_generator.next_id(),
                    user_id=user.id,
                    role_id=role.id,
                    create_time=now,
                    update_time=now,
                    create_user=None,
                    update_user=None,
                )
            )
            db.commit()

        user_group_member = db.scalar(
            select(TbUserGroupMember).where(
                TbUserGroupMember.user_id == user.id,
                TbUserGroupMember.group_id == group.id,
            )
        )
        if not user_group_member:
            db.add(
                TbUserGroupMember(
                    id=id_generator.next_id(),
                    user_id=user.id,
                    group_id=group.id,
                    create_time=now,
                    update_time=now,
                    create_user=None,
                    update_user=None,
                )
            )
            db.commit()
    finally:
        db.close()
