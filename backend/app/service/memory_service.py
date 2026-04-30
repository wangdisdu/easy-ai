"""长期记忆 KV 服务：upsert / forget / list / audit。

设计文档：agent-memory-design.md（已大幅简化）+ §6.4/6.5 现行实施记录。
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbApp, TbMemory, TbMemoryAudit
from app.model.memory_model import MemoryAuditResp, MemoryResp

logger = logging.getLogger(__name__)

VALID_SCOPES = {"user", "app"}
VALID_SOURCES = {"user_explicit", "agent_learned", "admin_set"}


# ── 鉴权 ────────────────────────────────────────────────────────────


def can_write_app_memory(db: Session, app_id: int, user_id: int | None) -> bool:
    """app scope 写入只允许 app owner（即 tb_app.create_user）。

    将来 user_role 接入后可扩展为 owner OR has_admin_role；本期只用 owner。
    """
    if user_id is None:
        return False
    app = db.get(TbApp, app_id)
    if not app:
        return False
    return app.create_user == user_id


# ── Service ────────────────────────────────────────────────────────


class MemoryService:
    """记忆 CRUD + 审计。"""

    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id = id_generator
        self._audit = MemoryAuditWriter(id_generator)

    # ── 读 ──

    def list_memories(
        self,
        db: Session,
        *,
        scope: str,
        scope_id: int,
        limit: int = 100,
    ) -> list[MemoryResp]:
        if scope not in VALID_SCOPES:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid scope: {scope}")
        rows = db.scalars(
            select(TbMemory)
            .where(TbMemory.scope == scope, TbMemory.scope_id == scope_id)
            .order_by(desc(TbMemory.update_time))
            .limit(limit)
        ).all()
        return [MemoryResp.from_entity(r) for r in rows]

    def get_top_for_injection(
        self, db: Session, *, scope: str, scope_id: int, top_n: int
    ) -> list[TbMemory]:
        """中间件注入热路径：直接返回 ORM 实体，省一道 dict 转换。"""
        return list(
            db.scalars(
                select(TbMemory)
                .where(TbMemory.scope == scope, TbMemory.scope_id == scope_id)
                .order_by(desc(TbMemory.update_time))
                .limit(top_n)
            ).all()
        )

    # ── 写 ──

    def upsert_memory(
        self,
        db: Session,
        *,
        scope: str,
        scope_id: int,
        memory_key: str,
        memory_value: str,
        source: str,
        actor_user_id: int | None,
        app_id: int | None = None,
        conversation_id: int | None = None,
    ) -> MemoryResp:
        if scope not in VALID_SCOPES:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid scope: {scope}")
        if source not in VALID_SOURCES:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid source: {source}")
        if not memory_key.strip():
            raise ServiceError(ErrorCode.BAD_REQUEST, "memory_key required")
        if not memory_value.strip():
            raise ServiceError(ErrorCode.BAD_REQUEST, "memory_value required")

        now = int(time.time() * 1000)
        existing = db.scalar(
            select(TbMemory).where(
                TbMemory.scope == scope,
                TbMemory.scope_id == scope_id,
                TbMemory.memory_key == memory_key,
            )
        )
        if existing is None:
            entity = TbMemory(
                id=self._id.next_id(),
                scope=scope,
                scope_id=scope_id,
                owner_user_id=actor_user_id,
                memory_key=memory_key,
                memory_value=memory_value,
                source=source,
                create_time=now,
                update_time=now,
                create_user=actor_user_id,
                update_user=actor_user_id,
            )
            db.add(entity)
            db.commit()
            db.refresh(entity)
            self._audit.write(
                db,
                event_type="remembered",
                scope=scope,
                scope_id=scope_id,
                memory_key=memory_key,
                memory_value_before=None,
                memory_value_after=memory_value,
                source=source,
                actor_user_id=actor_user_id,
                app_id=app_id,
                conversation_id=conversation_id,
            )
            return MemoryResp.from_entity(entity)

        before = existing.memory_value
        existing.memory_value = memory_value
        existing.source = source
        existing.update_time = now
        existing.update_user = actor_user_id
        db.commit()
        db.refresh(existing)
        self._audit.write(
            db,
            event_type="updated",
            scope=scope,
            scope_id=scope_id,
            memory_key=memory_key,
            memory_value_before=before,
            memory_value_after=memory_value,
            source=source,
            actor_user_id=actor_user_id,
            app_id=app_id,
            conversation_id=conversation_id,
        )
        return MemoryResp.from_entity(existing)

    def delete_memory(
        self,
        db: Session,
        *,
        scope: str,
        scope_id: int,
        memory_key: str,
        actor_user_id: int | None,
        app_id: int | None = None,
        conversation_id: int | None = None,
    ) -> bool:
        existing = db.scalar(
            select(TbMemory).where(
                TbMemory.scope == scope,
                TbMemory.scope_id == scope_id,
                TbMemory.memory_key == memory_key,
            )
        )
        if existing is None:
            return False
        before = existing.memory_value
        source = existing.source
        db.delete(existing)
        db.commit()
        self._audit.write(
            db,
            event_type="forgotten",
            scope=scope,
            scope_id=scope_id,
            memory_key=memory_key,
            memory_value_before=before,
            memory_value_after=None,
            source=source,
            actor_user_id=actor_user_id,
            app_id=app_id,
            conversation_id=conversation_id,
        )
        return True

    def purge_user_memories(self, db: Session, user_id: int, actor_user_id: int | None) -> int:
        """GDPR：删指定 user 的全部 user-scope 记忆，每条留一行 admin_purged 审计。"""
        rows = db.scalars(
            select(TbMemory).where(TbMemory.scope == "user", TbMemory.scope_id == user_id)
        ).all()
        if not rows:
            return 0
        for r in rows:
            self._audit.write(
                db,
                event_type="admin_purged",
                scope="user",
                scope_id=user_id,
                memory_key=r.memory_key,
                memory_value_before=r.memory_value,
                memory_value_after=None,
                source=r.source,
                actor_user_id=actor_user_id,
                app_id=None,
                conversation_id=None,
            )
        db.execute(delete(TbMemory).where(TbMemory.scope == "user", TbMemory.scope_id == user_id))
        db.commit()
        return len(rows)

    # ── 审计 ──

    def list_audit(
        self,
        db: Session,
        *,
        scope: str,
        scope_id: int,
        limit: int = 200,
    ) -> list[MemoryAuditResp]:
        rows = db.scalars(
            select(TbMemoryAudit)
            .where(TbMemoryAudit.scope == scope, TbMemoryAudit.scope_id == scope_id)
            .order_by(desc(TbMemoryAudit.id))
            .limit(limit)
        ).all()
        return [MemoryAuditResp.from_entity(r) for r in rows]


# ── Audit 写入 ─────────────────────────────────────────────────────


class MemoryAuditWriter:
    """tb_memory_audit 追加写。模仿 PolicyAuditWriter 的形态。

    每次写完不调 commit；调用方（MemoryService）在业务事务尾部统一 commit。
    """

    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id = id_generator

    def write(
        self,
        db: Session,
        *,
        event_type: str,
        scope: str,
        scope_id: int,
        memory_key: str,
        memory_value_before: str | None,
        memory_value_after: str | None,
        source: str,
        actor_user_id: int | None,
        app_id: int | None,
        conversation_id: int | None,
    ) -> None:
        try:
            db.add(
                TbMemoryAudit(
                    id=self._id.next_id(),
                    event_type=event_type,
                    scope=scope,
                    scope_id=scope_id,
                    memory_key=memory_key,
                    memory_value_before=memory_value_before,
                    memory_value_after=memory_value_after,
                    source=source,
                    actor_user_id=actor_user_id,
                    app_id=app_id,
                    conversation_id=conversation_id,
                    create_time=int(time.time() * 1000),
                )
            )
            db.commit()
        except Exception:
            logger.exception(
                "memory audit write failed: event=%s scope=%s key=%s",
                event_type,
                scope,
                memory_key,
            )
