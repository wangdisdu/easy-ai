"""指标聚合后台任务。

进程内定时任务,复刻 AlertRuleWorker 模式,在 lifespan 启停。每轮把尾部若干
分钟的 tb_app_log 聚合进 tb_app_metric_minute(UPSERT 幂等)。

只聚合「已完整结束」的分钟,当前分钟不算;故聚合表最多滞后约 1 分钟。长时间
停机产生的空洞需用 MetricRollupService.rebuild 补。

详见 docs/observability-metrics-rollup-design.md。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from sqlalchemy import text

from app.db.session import SessionLocal
from app.service.metric_rollup_service import MetricRollupService

logger = logging.getLogger(__name__)

# 全局 advisory lock key:同一时刻只允许一个 worker 进程聚合。
# 取小常量,不与 hitl(snowflake audit_id)、告警评估(90001)冲突。
METRIC_ROLLUP_LOCK_KEY = 90002

_MINUTE_MS = 60_000


class MetricRollupWorker:
    """定时把 tb_app_log 聚合进 tb_app_metric_minute。"""

    def __init__(self, *, interval_seconds: int, backfill_minutes: int) -> None:
        self._interval = interval_seconds
        self._backfill_minutes = backfill_minutes
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._service = MetricRollupService()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="metric-rollup-worker")
        logger.info(
            "metric rollup worker started: interval=%ds backfill=%dm",
            self._interval,
            self._backfill_minutes,
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
        logger.info("metric rollup worker stopped")

    async def _loop(self) -> None:
        # 启动后延迟 20s,待 web 就绪。
        if await self._sleep_or_stop(20):
            return
        while not self._stop_event.is_set():
            try:
                await asyncio.to_thread(self._run_once)
            except Exception:
                logger.exception("metric rollup worker iteration failed")
            if await self._sleep_or_stop(self._interval):
                return

    async def _sleep_or_stop(self, seconds: int) -> bool:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
            return True
        except TimeoutError:
            return False

    def _run_once(self) -> None:
        db = SessionLocal()
        try:
            # 抢全局 advisory lock;抢不到说明另一进程正在聚合,本轮跳过。
            got_lock = db.execute(
                text("SELECT pg_try_advisory_lock(:k)"),
                {"k": METRIC_ROLLUP_LOCK_KEY},
            ).scalar()
            if not got_lock:
                logger.debug("metric rollup skipped: lock held by another worker")
                return
            try:
                now_ms = int(time.time() * 1000)
                # 只聚合已完整结束的分钟:上界为当前分钟起点。
                to_ms = now_ms // _MINUTE_MS * _MINUTE_MS
                from_ms = to_ms - self._backfill_minutes * _MINUTE_MS
                n = self._service.roll_up(db, from_ms, to_ms)
                logger.debug("metric rollup done: %d bucket(s) upserted", n)
            finally:
                db.execute(
                    text("SELECT pg_advisory_unlock(:k)"),
                    {"k": METRIC_ROLLUP_LOCK_KEY},
                )
        finally:
            db.close()
