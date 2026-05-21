"""应用集成业务逻辑。

CRUD + Key 生成/重置/启停/删除 + 绑定关系增删 + Key hash 反查。
P1 类型(`agent_flow` / `kb_push`)在 service 层直接拒绝绑定,留待 P1 放开。
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from collections.abc import Iterable

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import (
    TbApiAccessLog,
    TbIntegration,
    TbIntegrationApp,
    TbIntegrationKey,
)
from app.db.session import SessionLocal
from app.model.integration_model import (
    SUPPORTED_APP_TYPES,
    ApiAccessLogPageReq,
    ApiAccessLogResp,
    BoundAppItem,
    IntegrationCreateReq,
    IntegrationCreateResp,
    IntegrationKeyPlaintextResp,
    IntegrationKeyResp,
    IntegrationKeyUpdateReq,
    IntegrationPageReq,
    IntegrationResp,
    IntegrationUpdateReq,
)

logger = logging.getLogger(__name__)

_KEY_PREFIX_LEN = 11  # 包含 `sk-prod-` 前缀
_KEY_SUFFIX_LEN = 4
_ERROR_MSG_MAX = 2000  # error_message 落库前截断长度


class IntegrationService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator

    # ── CRUD ──

    def page_integration(
        self, db: Session, req: IntegrationPageReq
    ) -> tuple[list[IntegrationResp], int]:
        stmt = select(TbIntegration).where(TbIntegration.deleted_at.is_(None))
        count_stmt = select(func.count(TbIntegration.id)).where(TbIntegration.deleted_at.is_(None))
        if req.keyword:
            kw = f"%{req.keyword}%"
            cond = or_(
                TbIntegration.name.like(kw),
                TbIntegration.description.like(kw),
            )
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)
        if req.status:
            stmt = stmt.where(TbIntegration.status == req.status)
            count_stmt = count_stmt.where(TbIntegration.status == req.status)

        total = db.scalar(count_stmt) or 0
        offset = (req.page_no - 1) * req.page_size
        rows = db.scalars(
            stmt.order_by(TbIntegration.create_time.desc()).offset(offset).limit(req.page_size)
        ).all()
        items = [self._hydrate(db, e) for e in rows]
        return items, total

    def get_integration(self, db: Session, intg_id: int) -> IntegrationResp:
        entity = self._require_active_integration(db, intg_id)
        return self._hydrate(db, entity)

    def create_integration(
        self, db: Session, req: IntegrationCreateReq, req_ctx: RequestContext
    ) -> IntegrationCreateResp:
        self._assert_supported_bindings(req.bound_apps)
        if db.scalar(
            select(TbIntegration).where(
                and_(
                    TbIntegration.name == req.name,
                    TbIntegration.deleted_at.is_(None),
                )
            )
        ):
            raise ServiceError(
                ErrorCode.INTEGRATION_NAME_DUPLICATE, "integration name already exists"
            )

        now = req_ctx.request_time_ms
        intg = TbIntegration(
            id=self._id_generator.next_id(),
            name=req.name,
            description=req.description,
            status="active",
            quota=req.quota,
            rate_limit=req.rate_limit,
            timeout=req.timeout,
            whitelist=req.whitelist,
            expire_at=req.expire_at,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(intg)
        db.flush()

        self._replace_bindings(db, intg.id, req.bound_apps, now)

        # 首把 Key:即便此处异常,集成本体已 commit 不会回滚 → 前端弹"请手动创建"
        first_key_plain: IntegrationKeyPlaintextResp | None = None
        try:
            first_key_plain = self._issue_key(
                db, integration_id=intg.id, now=now, user_id=req_ctx.user_id
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("first api key generation failed for integration %s", intg.id)

        db.commit()
        db.refresh(intg)
        return IntegrationCreateResp(integration=self._hydrate(db, intg), first_key=first_key_plain)

    def update_integration(
        self,
        db: Session,
        intg_id: int,
        req: IntegrationUpdateReq,
        req_ctx: RequestContext,
    ) -> IntegrationResp:
        if req.bound_apps is not None:
            self._assert_supported_bindings(req.bound_apps)
        entity = self._require_active_integration(db, intg_id)

        # 用 model_fields_set 区分"未提供"与"显式置 null":
        # - 字段不在请求体里 → 不修改
        # - 字段在请求体里且为 null → 写回 NULL
        #   (quota/rate_limit/timeout 的 NULL 即"继承全局默认",见 §3.4)
        fields = req.model_fields_set

        if "name" in fields and req.name is not None and req.name != entity.name:
            dup = db.scalar(
                select(TbIntegration).where(
                    and_(
                        TbIntegration.name == req.name,
                        TbIntegration.id != intg_id,
                        TbIntegration.deleted_at.is_(None),
                    )
                )
            )
            if dup:
                raise ServiceError(
                    ErrorCode.INTEGRATION_NAME_DUPLICATE, "integration name already exists"
                )
            entity.name = req.name

        if "description" in fields:
            entity.description = req.description
        if "quota" in fields:
            entity.quota = req.quota
        if "rate_limit" in fields:
            entity.rate_limit = req.rate_limit
        if "timeout" in fields:
            entity.timeout = req.timeout
        if "whitelist" in fields:
            entity.whitelist = req.whitelist
        if "expire_at" in fields:
            entity.expire_at = req.expire_at

        now = req_ctx.request_time_ms
        entity.update_time = now
        entity.update_user = req_ctx.user_id

        if req.bound_apps is not None:
            self._replace_bindings(db, intg_id, req.bound_apps, now)

        db.commit()
        db.refresh(entity)
        return self._hydrate(db, entity)

    def set_status(
        self,
        db: Session,
        intg_id: int,
        status: str,
        req_ctx: RequestContext,
    ) -> IntegrationResp:
        entity = self._require_active_integration(db, intg_id)
        entity.status = status
        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        return self._hydrate(db, entity)

    def delete_integration(self, db: Session, intg_id: int, req_ctx: RequestContext) -> None:
        entity = self._require_active_integration(db, intg_id)
        now = req_ctx.request_time_ms
        entity.deleted_at = now
        entity.update_time = now
        entity.update_user = req_ctx.user_id
        # 同步标记所有 Key 软删除,避免拿着已删除集成的 Key 通过鉴权
        active_keys = db.scalars(
            select(TbIntegrationKey).where(
                and_(
                    TbIntegrationKey.integration_id == intg_id,
                    TbIntegrationKey.deleted_at.is_(None),
                )
            )
        ).all()
        for k in active_keys:
            k.deleted_at = now
        db.commit()

    # ── Key 管理 ──

    def create_key(
        self, db: Session, intg_id: int, req_ctx: RequestContext
    ) -> IntegrationKeyPlaintextResp:
        self._require_active_integration(db, intg_id)
        now = req_ctx.request_time_ms
        plain = self._issue_key(db, integration_id=intg_id, now=now, user_id=req_ctx.user_id)
        db.commit()
        return plain

    def update_key(
        self,
        db: Session,
        intg_id: int,
        key_id: int,
        req: IntegrationKeyUpdateReq,
    ) -> IntegrationKeyResp:
        key = self._require_active_key(db, intg_id, key_id)
        if req.rate_limit_inherit:
            key.rate_limit = None
        elif req.rate_limit is not None:
            key.rate_limit = req.rate_limit
        if req.status is not None:
            key.status = req.status
        db.commit()
        db.refresh(key)
        return IntegrationKeyResp.from_entity(key)

    def reset_key(
        self,
        db: Session,
        intg_id: int,
        key_id: int,
        req_ctx: RequestContext,
    ) -> IntegrationKeyPlaintextResp:
        old = self._require_active_key(db, intg_id, key_id)
        now = req_ctx.request_time_ms
        old.revoked_at = now
        plain = self._issue_key(
            db,
            integration_id=intg_id,
            now=now,
            user_id=req_ctx.user_id,
            inherited_rate_limit=old.rate_limit,
        )
        db.commit()
        return plain

    def delete_key(self, db: Session, intg_id: int, key_id: int, req_ctx: RequestContext) -> None:
        key = self._require_active_key(db, intg_id, key_id)
        key.deleted_at = req_ctx.request_time_ms
        db.commit()

    # ── 内部工具 ──

    def lookup_by_key_plain(
        self, db: Session, plaintext: str
    ) -> tuple[TbIntegration, TbIntegrationKey] | None:
        """对外网关鉴权:用明文 Key 反查 (Integration, Key)。

        网关层调用此方法时已经通过 Bearer 拿到明文,这里仅做 hash 反查 +
        基础有效性校验(未撤销/未删除/未停用)。集成本身的状态与过期由调用方再判。
        """
        key_hash = _hash_key(plaintext)
        key = db.scalar(select(TbIntegrationKey).where(TbIntegrationKey.key_hash == key_hash))
        if key is None or key.deleted_at is not None or key.revoked_at is not None:
            return None
        intg = db.scalar(
            select(TbIntegration).where(
                and_(
                    TbIntegration.id == key.integration_id,
                    TbIntegration.deleted_at.is_(None),
                )
            )
        )
        if intg is None:
            return None
        return intg, key

    def is_app_bound(self, db: Session, intg_id: int, app_type: str, app_id: int) -> bool:
        row = db.scalar(
            select(TbIntegrationApp).where(
                and_(
                    TbIntegrationApp.integration_id == intg_id,
                    TbIntegrationApp.app_type == app_type,
                    TbIntegrationApp.app_id == app_id,
                )
            )
        )
        return row is not None

    # ── 调用日志 ──

    def record_access_log(
        self,
        *,
        integration_id: int | None,
        key_id: int | None,
        app_type: str | None,
        app_id: int | None,
        status_code: int,
        code: str,
        reason: str | None = None,
        latency_ms: int | None = None,
        client_ip: str | None = None,
        request_bytes: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """写一条网关调用日志。

        用独立 session:调用方(网关 handler / 502 路径)的请求 session 可能已处于
        失败事务态。任何异常都吞掉,日志写入绝不能影响主响应。
        """
        try:
            db = SessionLocal()
            try:
                db.add(
                    TbApiAccessLog(
                        id=self._id_generator.next_id(),
                        integration_id=integration_id,
                        key_id=key_id,
                        app_type=app_type,
                        app_id=app_id,
                        status_code=status_code,
                        code=code,
                        reason=reason,
                        latency_ms=latency_ms,
                        client_ip=client_ip,
                        request_bytes=request_bytes,
                        error_message=(error_message[:_ERROR_MSG_MAX] if error_message else None),
                        create_time=int(time.time() * 1000),
                    )
                )
                db.commit()
            finally:
                db.close()
        except Exception:  # pragma: no cover - 日志失败不影响主流程
            logger.warning("failed to record api access log", exc_info=True)

    def page_access_log(
        self, db: Session, req: ApiAccessLogPageReq
    ) -> tuple[list[ApiAccessLogResp], int]:
        stmt = select(TbApiAccessLog)
        count_stmt = select(func.count(TbApiAccessLog.id))
        if req.integration_id:
            iid = int(req.integration_id)
            stmt = stmt.where(TbApiAccessLog.integration_id == iid)
            count_stmt = count_stmt.where(TbApiAccessLog.integration_id == iid)
        if req.only_failed:
            stmt = stmt.where(TbApiAccessLog.status_code >= 400)
            count_stmt = count_stmt.where(TbApiAccessLog.status_code >= 400)

        total = db.scalar(count_stmt) or 0
        offset = (req.page_no - 1) * req.page_size
        rows = db.scalars(
            stmt.order_by(TbApiAccessLog.create_time.desc()).offset(offset).limit(req.page_size)
        ).all()
        return [ApiAccessLogResp.from_entity(r) for r in rows], total

    # ── private helpers ──

    def _hydrate(self, db: Session, entity: TbIntegration) -> IntegrationResp:
        bindings = db.scalars(
            select(TbIntegrationApp).where(TbIntegrationApp.integration_id == entity.id)
        ).all()
        keys = db.scalars(
            select(TbIntegrationKey)
            .where(
                and_(
                    TbIntegrationKey.integration_id == entity.id,
                    TbIntegrationKey.deleted_at.is_(None),
                )
            )
            .order_by(TbIntegrationKey.create_time.desc())
        ).all()
        return IntegrationResp.from_entity(entity, bindings=list(bindings), keys=list(keys))

    def _require_active_integration(self, db: Session, intg_id: int) -> TbIntegration:
        entity = db.scalar(
            select(TbIntegration).where(
                and_(
                    TbIntegration.id == intg_id,
                    TbIntegration.deleted_at.is_(None),
                )
            )
        )
        if entity is None:
            raise ServiceError(ErrorCode.INTEGRATION_NOT_FOUND, "integration not found")
        return entity

    def _require_active_key(self, db: Session, intg_id: int, key_id: int) -> TbIntegrationKey:
        key = db.scalar(
            select(TbIntegrationKey).where(
                and_(
                    TbIntegrationKey.id == key_id,
                    TbIntegrationKey.integration_id == intg_id,
                    TbIntegrationKey.deleted_at.is_(None),
                )
            )
        )
        if key is None:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "api key not found")
        return key

    def _assert_supported_bindings(self, items: Iterable[BoundAppItem]) -> None:
        for item in items:
            if item.app_type not in SUPPORTED_APP_TYPES:
                raise ServiceError(
                    ErrorCode.INTEGRATION_BIND_NOT_ALLOWED,
                    f"binding app_type '{item.app_type}' is not supported yet",
                )

    def _replace_bindings(
        self,
        db: Session,
        intg_id: int,
        items: Iterable[BoundAppItem],
        now: int,
    ) -> None:
        db.execute(
            TbIntegrationApp.__table__.delete().where(TbIntegrationApp.integration_id == intg_id)
        )
        seen: set[tuple[str, int]] = set()
        for item in items:
            try:
                app_id = int(item.app_id)
            except (TypeError, ValueError) as e:
                raise ServiceError(ErrorCode.BAD_REQUEST, "invalid app_id") from e
            sig = (item.app_type, app_id)
            if sig in seen:
                continue
            seen.add(sig)
            db.add(
                TbIntegrationApp(
                    integration_id=intg_id,
                    app_type=item.app_type,
                    app_id=app_id,
                    create_time=now,
                )
            )
        db.flush()

    def _issue_key(
        self,
        db: Session,
        *,
        integration_id: int,
        now: int,
        user_id: int | None,
        inherited_rate_limit: int | None = None,
    ) -> IntegrationKeyPlaintextResp:
        plaintext = _generate_key()
        key = TbIntegrationKey(
            id=self._id_generator.next_id(),
            integration_id=integration_id,
            key_prefix=plaintext[:_KEY_PREFIX_LEN],
            key_suffix=plaintext[-_KEY_SUFFIX_LEN:],
            key_hash=_hash_key(plaintext),
            status="active",
            rate_limit=inherited_rate_limit,
            create_time=now,
            create_user=user_id,
        )
        db.add(key)
        db.flush()
        return IntegrationKeyPlaintextResp(
            key=IntegrationKeyResp.from_entity(key), plaintext=plaintext
        )


# ── module-level helpers ──


def _generate_key() -> str:
    """生成形如 `sk-prod-{32 hex 字符}` 的 API Key。"""
    return f"sk-prod-{secrets.token_hex(16)}"


def _hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
