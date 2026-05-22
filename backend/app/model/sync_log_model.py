"""同步日志模型 —— 知识集成 / 知识向量化 的执行记录。

详见 ``docs/knowledge-v2-design.md`` §4.6 / §7。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.db.schema import TbSyncLog

# 日志类型
VALID_LOG_TYPES = {"integration", "vectorization"}


class SyncLogPageReq(BaseModel):
    page_no: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=10000)
    # integration / vectorization; None=不限
    log_type: str | None = Field(default=None, max_length=32)
    status: str | None = Field(default=None, max_length=32)


class SyncLogResp(BaseModel):
    id: str
    log_type: str
    source_type: str | None = None
    source_name: str | None = None
    target_kb_id: str | None = None
    target_dataset_id: str | None = None
    docs_added: int = 0
    docs_updated: int = 0
    docs_deleted: int = 0
    chunks_created: int = 0
    status: str
    duration_ms: int | None = None
    detail: str | None = None
    create_time: int

    @classmethod
    def from_entity(cls, entity: TbSyncLog) -> SyncLogResp:
        return cls(
            id=str(entity.id),
            log_type=entity.log_type,
            source_type=entity.source_type,
            source_name=entity.source_name,
            target_kb_id=str(entity.target_kb_id) if entity.target_kb_id else None,
            target_dataset_id=(str(entity.target_dataset_id) if entity.target_dataset_id else None),
            docs_added=entity.docs_added,
            docs_updated=entity.docs_updated,
            docs_deleted=entity.docs_deleted,
            chunks_created=entity.chunks_created,
            status=entity.status,
            duration_ms=entity.duration_ms,
            detail=entity.detail,
            create_time=entity.create_time,
        )
