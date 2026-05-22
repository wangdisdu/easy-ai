"""知识向量化后台 worker。

周期驱动 ``VectorizationService.run_once``:把 ``pending`` 文档推送到 RAGFlow,
并回拉 ``parsing`` 文档的解析进度。复刻 ``HitlTimeoutWorker`` 的进程内定时模式。

- 进程启动时 ``start()`` 拉起单个 asyncio 任务
- 默认 30s 一轮(``kb_status_poll_interval_seconds``)
- RAGFlow 不可达 / 单轮失败仅日志,下一轮继续

详见 ``docs/knowledge-v2-design.md`` §7。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from app.core.config import settings
from app.core.snowflake import SnowflakeGenerator
from app.db.session import SessionLocal
from app.service.vectorization_service import VectorizationService

logger = logging.getLogger(__name__)


class VectorizationWorker:
    """周期推送 / 回拉知识向量化状态。"""

    def __init__(self, *, interval_seconds: int) -> None:
        self._interval = max(5, interval_seconds)
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._service = VectorizationService(SnowflakeGenerator(settings.snowflake_worker_id))

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="vectorization-worker")
        logger.info("vectorization worker started: interval=%ds", self._interval)

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
        logger.info("vectorization worker stopped")

    async def _loop(self) -> None:
        # 启动后延迟一轮, 让 RAGFlow 就绪, 避免冷启动噪音
        if await self._sleep_or_stop(self._interval):
            return
        while not self._stop_event.is_set():
            try:
                await asyncio.to_thread(self._run_once)
            except Exception:
                logger.exception("vectorization worker iteration failed")
            if await self._sleep_or_stop(self._interval):
                return

    async def _sleep_or_stop(self, seconds: int) -> bool:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
            return True
        except TimeoutError:
            return False

    def _run_once(self) -> None:
        if not settings.ragflow_enabled:
            return
        db = SessionLocal()
        try:
            touched = self._service.run_once(db)
            if touched:
                logger.info("[vectorize] worker touched %d doc(s)", touched)
        except Exception:
            logger.exception("vectorization worker run_once failed")
        finally:
            with contextlib.suppress(Exception):
                db.close()
