"""告警规则评估后台任务。

进程内定时模式,复刻 HitlTimeoutWorker / CheckpointPurger:
- 每个 worker 进程都会启动它
- 每轮先抢一把 Postgres advisory lock,抢到的进程才执行评估,避免多 worker
  在同一时刻重复评估、重复落告警记录(规则自身的 cooldown 是第二道防线)
- 逐条调用 AlertEvaluator.evaluate

详见 docs/observability-alert-design.md。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbAlertRule
from app.db.session import SessionLocal
from app.service.alert_evaluator import AlertEvaluator

logger = logging.getLogger(__name__)

# 全局 advisory lock key:同一时刻只允许一个 worker 进程评估告警规则。
# 取小常量,不与 hitl worker 用的 snowflake audit_id（极大数）冲突。
ALERT_EVAL_LOCK_KEY = 90001


class AlertRuleWorker:
    """定时扫描 enabled=1 的告警规则并评估。"""

    def __init__(self, *, interval_seconds: int) -> None:
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._evaluator = AlertEvaluator(SnowflakeGenerator(settings.snowflake_worker_id))

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="alert-rule-worker")
        logger.info("alert rule worker started: interval=%ds", self._interval)

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
        logger.info("alert rule worker stopped")

    async def _loop(self) -> None:
        # 启动后延迟 30s,让 web 全部就绪、积累一点 tb_app_log 后再评估。
        if await self._sleep_or_stop(30):
            return
        while not self._stop_event.is_set():
            try:
                # 评估含 DB 同步 IO,丢到线程池避免阻塞事件循环。
                await asyncio.to_thread(self._run_once)
            except Exception:
                logger.exception("alert rule worker iteration failed")
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
            # 抢全局 advisory lock;抢不到说明另一个 worker 正在评估,本轮跳过。
            got_lock = db.execute(
                text("SELECT pg_try_advisory_lock(:k)"),
                {"k": ALERT_EVAL_LOCK_KEY},
            ).scalar()
            if not got_lock:
                logger.debug("alert eval skipped: lock held by another worker")
                return
            try:
                self._evaluate_all(db)
            finally:
                db.execute(
                    text("SELECT pg_advisory_unlock(:k)"),
                    {"k": ALERT_EVAL_LOCK_KEY},
                )
        finally:
            db.close()

    def _evaluate_all(self, db: Session) -> None:
        rules = db.scalars(select(TbAlertRule).where(TbAlertRule.enabled == 1)).all()
        if not rules:
            return
        now_ms = int(time.time() * 1000)
        fired = 0
        for rule in rules:
            try:
                result = self._evaluator.evaluate(db, rule, now_ms=now_ms)
                if result.triggered and result.record_id:
                    fired += 1
            except Exception:
                # 单条规则失败不影响其余规则。evaluate 内的写操作各自 commit。
                db.rollback()
                logger.exception("alert rule evaluation failed: rule_id=%s", rule.id)
        logger.info("alert eval done: %d rule(s) scanned, %d new alert(s)", len(rules), fired)
