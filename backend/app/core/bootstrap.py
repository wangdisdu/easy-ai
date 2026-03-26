import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbUser
from app.db.session import SessionLocal
from app.model.user_model import UserCreateReq
from app.service.user_service import UserService

logger = logging.getLogger(__name__)

DEFAULT_ADMIN_ACCOUNT = "admin"
DEFAULT_ADMIN_PASSWD = "admin"


def ensure_default_admin() -> None:
    """若不存在账号 admin，则创建默认管理员（admin / admin）。"""
    db: Session = SessionLocal()
    try:
        exists = db.scalar(select(TbUser).where(TbUser.account == DEFAULT_ADMIN_ACCOUNT))
        if exists:
            return
        now = int(time.time() * 1000)
        ctx = RequestContext(user_id=None, client_ip=None, request_time_ms=now)
        svc = UserService(SnowflakeGenerator(settings.snowflake_worker_id))
        svc.create_user(
            db,
            UserCreateReq(account=DEFAULT_ADMIN_ACCOUNT, passwd=DEFAULT_ADMIN_PASSWD),
            ctx,
        )
        logger.info("default admin user created: %s", DEFAULT_ADMIN_ACCOUNT)
    finally:
        db.close()
