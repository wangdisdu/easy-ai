"""同步日志 API 路由(/api/v1/sync-log)。

知识集成 / 知识向量化 的执行记录,只读。详见 ``docs/knowledge-v2-design.md``。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.response import PagedResp
from app.core.snowflake import SnowflakeGenerator
from app.db.session import get_db
from app.model.sync_log_model import SyncLogPageReq, SyncLogResp
from app.service.sync_log_service import SyncLogService

router = APIRouter(prefix="/sync-log", tags=["sync-log"])
service = SyncLogService(SnowflakeGenerator(settings.snowflake_worker_id))


@router.get("/page", response_model=PagedResp[SyncLogResp])
def page_sync_logs(
    page_no: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=10000),
    log_type: str | None = Query(default=None, description="integration / vectorization"),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> PagedResp[SyncLogResp]:
    data, total = service.page(
        db=db,
        req=SyncLogPageReq(page_no=page_no, page_size=page_size, log_type=log_type, status=status),
    )
    return PagedResp(data=data, total=total)
