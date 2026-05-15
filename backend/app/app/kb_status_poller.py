"""KB 文档解析状态后台回拉。

RAGFlow 解析是异步的(文档 ``run`` 状态从 ``UNSTART`` → ``RUNNING`` → ``DONE/FAIL``),
前端按需轮询打开的文档,但列表页 / 批量场景仍需后台周期性回拉,避免文档长期停在
``parsing`` 状态。

实现思路(复刻 HitlTimeoutWorker / CheckpointPurger 的进程内定时模式):
- 进程启动时 ``start()`` 拉起单个 asyncio 任务
- 默认 30s 一轮; 每轮按 kb_id 分组扫 ``parse_status in (pending,parsing)`` 的文档
- 每组调一次 ``RagflowClient.list_documents`` 拉对账, 由
  ``KbDocumentService.batch_sync_status`` 完成字段更新
- RAGFlow 不可达 / 单组失败仅日志, 下一轮继续

详见 ``docs/knowledge-rag-integration-design.md`` §5.6。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbKb, TbKbDocument
from app.db.session import SessionLocal
from app.service.kb_document_service import KbDocumentService

logger = logging.getLogger(__name__)


class KbStatusPoller:
    """周期回拉 RAGFlow 文档解析状态。"""

    def __init__(self, *, interval_seconds: int) -> None:
        self._interval = max(5, interval_seconds)
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._doc_service = KbDocumentService(SnowflakeGenerator(settings.snowflake_worker_id))

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="kb-status-poller")
        logger.info("kb status poller started: interval=%ds", self._interval)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except TimeoutError:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._task = None
        logger.info("kb status poller stopped")

    async def _loop(self) -> None:
        # 启动后延迟一轮让 RAGFlow 与 web 都就绪, 避免冷启动期间报噪音
        if await self._sleep_or_stop(self._interval):
            return
        while not self._stop_event.is_set():
            try:
                # 阻塞 DB / HTTP 走 to_thread, 避免占住事件循环
                await asyncio.to_thread(self._run_once)
            except Exception:
                logger.exception("kb status poller iteration failed")
            if await self._sleep_or_stop(self._interval):
                return

    async def _sleep_or_stop(self, seconds: int) -> bool:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
            return True
        except TimeoutError:
            return False

    def _run_once(self) -> None:
        # ragflow 关闭时直接跳过, 避免持续报错
        if not settings.ragflow_enabled:
            return
        groups = self._fetch_kb_groups_with_pending()
        if not groups:
            return
        logger.info("kb status poller: %d kb(s) with pending docs", len(groups))
        now_ms = int(time.time() * 1000)
        for kb_id, dataset_id in groups:
            db = SessionLocal()
            try:
                updated = self._doc_service.batch_sync_status(db, kb_id, dataset_id, now_ms)
                if updated:
                    logger.info("[kb] poller updated kb_id=%s docs=%d", kb_id, updated)
            except Exception:
                logger.exception("kb status poller failed kb_id=%s", kb_id)
            finally:
                with contextlib.suppress(Exception):
                    db.close()

    def _fetch_kb_groups_with_pending(self) -> list[tuple[int, str]]:
        """选出当前有 pending/parsing 文档的 KB 列表(去重 + 跟它们的 dataset_id)。
        不返回没有 ragflow_dataset_id 的 KB(无意义)。
        """
        db: Session = SessionLocal()
        try:
            sub = (
                select(TbKbDocument.kb_id)
                .where(TbKbDocument.parse_status.in_(("pending", "parsing")))
                .distinct()
            )
            stmt = select(TbKb.id, TbKb.ragflow_dataset_id).where(
                TbKb.id.in_(sub),
                TbKb.ragflow_dataset_id.is_not(None),
            )
            return [(row.id, row.ragflow_dataset_id) for row in db.execute(stmt).all()]
        finally:
            db.close()
