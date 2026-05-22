from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.app.alert_rule_worker import AlertRuleWorker
from app.app.checkpoint_purger import CheckpointPurger
from app.app.checkpointer_factory import get_checkpointer_factory
from app.app.hitl_timeout_worker import HitlTimeoutWorker
from app.app.metric_rollup_worker import MetricRollupWorker
from app.app.vectorization_worker import VectorizationWorker
from app.core.bootstrap import ensure_default_admin
from app.core.config import settings
from app.core.rate_limit import MemoryRateLimiter
from app.integration import ragflow_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """FastAPI 生命周期：启动期初始化共享资源，关闭期释放。"""
    # 默认 admin 种子保留原行为。
    ensure_default_admin()

    # 应用集成限流器(P0 单机内存,详见 docs/application-integration-design.md §9)
    limiter = MemoryRateLimiter()
    await limiter.start_janitor()
    _app.state.limiter = limiter

    factory = get_checkpointer_factory()
    await factory.start()

    purger: CheckpointPurger | None = None
    if settings.purge_enabled:
        purger = CheckpointPurger(
            interval_seconds=settings.purge_interval_seconds,
            ttl_days=settings.purge_ttl_days,
        )
        await purger.start()

    hitl_worker = HitlTimeoutWorker(
        interval_seconds=settings.hitl_timeout_check_interval_seconds,
        default_timeout_seconds=settings.hitl_timeout_seconds,
    )
    await hitl_worker.start()

    vectorize_worker: VectorizationWorker | None = None
    if settings.ragflow_enabled:
        vectorize_worker = VectorizationWorker(
            interval_seconds=settings.kb_status_poll_interval_seconds,
        )
        await vectorize_worker.start()

    alert_worker: AlertRuleWorker | None = None
    if settings.alert_eval_enabled:
        alert_worker = AlertRuleWorker(
            interval_seconds=settings.alert_eval_interval_seconds,
        )
        await alert_worker.start()

    metric_rollup_worker: MetricRollupWorker | None = None
    if settings.metric_rollup_enabled:
        metric_rollup_worker = MetricRollupWorker(
            interval_seconds=settings.metric_rollup_interval_seconds,
            backfill_minutes=settings.metric_rollup_backfill_minutes,
        )
        await metric_rollup_worker.start()

    try:
        yield
    finally:
        if metric_rollup_worker is not None:
            await metric_rollup_worker.stop()
        if alert_worker is not None:
            await alert_worker.stop()
        if vectorize_worker is not None:
            await vectorize_worker.stop()
        await hitl_worker.stop()
        if purger is not None:
            await purger.stop()
        await limiter.stop_janitor()
        # 关闭 ragflow httpx 连接池
        ragflow_client.close_client()
        await factory.close()
        logger.info("checkpointer closed")
