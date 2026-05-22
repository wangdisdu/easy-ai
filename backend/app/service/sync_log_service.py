"""同步日志业务层 —— 知识集成 / 知识向量化 的执行记录。

``write`` 落一条审计记录并即时 commit,调用方应在主业务提交后再调用它。
详见 ``docs/knowledge-v2-design.md``。
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbSyncLog
from app.model.sync_log_model import SyncLogPageReq, SyncLogResp

logger = logging.getLogger(__name__)


class SyncLogService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator

    def write(
        self,
        db: Session,
        *,
        log_type: str,
        status: str,
        source_type: str | None = None,
        source_name: str | None = None,
        target_kb_id: int | None = None,
        target_dataset_id: int | None = None,
        docs_added: int = 0,
        docs_updated: int = 0,
        docs_deleted: int = 0,
        chunks_created: int = 0,
        duration_ms: int | None = None,
        detail: str | None = None,
        create_user: int | None = None,
    ) -> None:
        """落一条同步日志并 commit。失败仅记日志,不向上抛(审计不应阻断主流程)。"""
        try:
            db.add(
                TbSyncLog(
                    id=self._id_generator.next_id(),
                    log_type=log_type,
                    source_type=source_type,
                    source_name=source_name,
                    target_kb_id=target_kb_id,
                    target_dataset_id=target_dataset_id,
                    docs_added=docs_added,
                    docs_updated=docs_updated,
                    docs_deleted=docs_deleted,
                    chunks_created=chunks_created,
                    status=status,
                    duration_ms=duration_ms,
                    detail=(detail or "")[:2048] or None,
                    create_time=int(time.time() * 1000),
                    create_user=create_user,
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("[sync_log] write failed log_type=%s", log_type)

    def page(self, db: Session, req: SyncLogPageReq) -> tuple[list[SyncLogResp], int]:
        stmt = select(TbSyncLog)
        count_stmt = select(func.count(TbSyncLog.id))
        conditions = []
        if req.log_type:
            conditions.append(TbSyncLog.log_type == req.log_type)
        if req.status:
            conditions.append(TbSyncLog.status == req.status)
        if conditions:
            stmt = stmt.where(*conditions)
            count_stmt = count_stmt.where(*conditions)

        total = db.scalar(count_stmt) or 0
        rows = db.scalars(
            stmt.order_by(TbSyncLog.create_time.desc())
            .offset((req.page_no - 1) * req.page_size)
            .limit(req.page_size)
        ).all()
        return [SyncLogResp.from_entity(r) for r in rows], total
