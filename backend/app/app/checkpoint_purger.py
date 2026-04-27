from __future__ import annotations

import asyncio
import contextlib
import logging

from sqlalchemy import text

from app.core.config import settings
from app.core.snowflake import SnowflakeGenerator
from app.db.session import SessionLocal
from app.service.conversation_service import ConversationService

logger = logging.getLogger(__name__)

# 任意但稳定的 64-bit 整数；给 Postgres advisory lock 用，
# 多 worker 时只有抢到这把锁的进程实际跑 purge，避免重复扫描和冲突。
# 0xEA51A1C0DE = "EASYAICODE"，仅做记忆助记，无业务含义。
_ADVISORY_LOCK_KEY = 0xEA51A1C0DE


class CheckpointPurger:
    """进程内 checkpoint 定时清理任务。

    多 worker 部署下所有进程都会启动它，但通过 Postgres advisory lock
    保证同一时刻只有一个 worker 在真正执行扫描；其他 worker 抢锁失败直接跳过。
    """

    def __init__(self, *, interval_seconds: int, ttl_days: int) -> None:
        self._interval = interval_seconds
        self._ttl_days = ttl_days
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="checkpoint-purger")
        logger.info(
            "checkpoint purger started: interval=%ds ttl=%dd",
            self._interval,
            self._ttl_days,
        )

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
        logger.info("checkpoint purger stopped")

    async def _loop(self) -> None:
        # 启动后延迟 60s 再首次扫，避开滚动部署时多个新 worker 同时抢锁。
        if await self._sleep_or_stop(60):
            return

        while not self._stop_event.is_set():
            try:
                await self._run_once()
            except Exception:
                logger.exception("checkpoint purger iteration failed")
            if await self._sleep_or_stop(self._interval):
                return

    async def _sleep_or_stop(self, seconds: int) -> bool:
        """睡 seconds 秒；中途收到 stop 信号则提前返回 True。"""
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
            return True
        except TimeoutError:
            return False

    async def _run_once(self) -> None:
        db = SessionLocal()
        try:
            got_lock = db.execute(
                text("SELECT pg_try_advisory_lock(:k)"),
                {"k": _ADVISORY_LOCK_KEY},
            ).scalar()
            if not got_lock:
                logger.debug("checkpoint purger: another worker holds lock, skipping")
                return
            try:
                conv_service = ConversationService(SnowflakeGenerator(settings.snowflake_worker_id))
                count = await conv_service.purge_expired_checkpoints(db, ttl_days=self._ttl_days)
                if count:
                    logger.info("checkpoint purger: purged %d threads", count)
            finally:
                db.execute(
                    text("SELECT pg_advisory_unlock(:k)"),
                    {"k": _ADVISORY_LOCK_KEY},
                )
        finally:
            db.close()
